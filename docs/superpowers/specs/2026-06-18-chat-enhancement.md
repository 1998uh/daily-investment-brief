# 对话功能增强 — 设计规格

**日期**：2026-06-18  
**状态**：已确认，待实现  
**范围**：Agent 层 + 前端（pipeline/ 不动）

---

## 背景与目标

当前 Agent 对话存在三个核心短板：
1. **纯文本输入**：用户无法上传 PDF/图片等文件让 AI 理解
2. **无联网能力**：只有本地 ChromaDB 语义检索，无法获取实时市场信息
3. **伪流式输出**：同步调用 `pipeline.llm.chat_completion` 后模拟分块，响应延迟高

**增强目标：**
1. 支持文件上传（txt/md/pdf/csv + png/jpg 图片），图片通过多模态 LLM（Vision）理解
2. 集成 Tavily 实时网络搜索，补充本地 RAG 不足
3. 真正逐 token 流式输出，实现打字机效果

**约束：**
- pipeline/ 层完全不动，不修改 `pipeline/llm.py`
- 在 agent 层新建独立的流式 LLM 客户端
- 保留 fallback：流式不可用时降级到同步 pipeline.llm

---

## Feature 1: 真正流式 LLM

### 问题

当前 `agent/agents/orchestrator.py` 调用 `pipeline.llm.chat_completion()`（同步、返回完整文本），再用 `_split_to_chunks()` 按 50 字符切块模拟流式。用户体验：等待 5-10 秒后一次性"快进"输出。

### 方案

在 `agent/` 层新建 `agent/llm.py`，实现异步流式 OpenAI-compatible 客户端：

```python
async def stream_chat_completion(
    settings: AgentSettings,
    messages: list[dict],
    *,
    temperature: float | None = None,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
```

- 使用 `httpx.AsyncClient` 调用 `{settings.llm_base_url}/chat/completions`
- 请求 body 设 `"stream": true`
- 逐行解析 SSE 响应：`data: {...}` → yield `choices[0].delta.content`
- 处理 `data: [DONE]` 结束迭代
- HTTP 错误 / 超时抛 `LLMStreamError`

### Orchestrator 改动

- 删除 `_split_to_chunks` 函数
- LLM 调用块改为：
  ```python
  from agent.llm import stream_chat_completion
  async for delta in stream_chat_completion(settings, messages):
      yield _sse("token", text=delta)
  ```
- 异常时 fallback 到同步 `pipeline.llm.chat_completion`

### 新增依赖

```toml
# pyproject.toml [project.optional-dependencies] agent
"httpx>=0.27"
```

---

## Feature 2: 实时网络搜索（Tavily）

### 问题

用户问"最新美股行情"等实时问题时，本地 ChromaDB 只有历史文章，无法回答。

### 方案

集成 Tavily API（已在 pyproject.toml 依赖中：`tavily-python>=0.3`）。

### 工具函数

`agent/agents/tools.py` 新增：

```python
async def tool_search_web(
    settings: AgentSettings,
    query: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
```

- 用 `TavilyClient(api_key=settings.tavily_api_key)`
- 通过 `asyncio.to_thread(client.search, ...)` 包装为异步
- 返回结构对齐 `tool_search_local`：
  ```json
  [{"content": "...", "metadata": {"title", "url", "source": "tavily", "kind": "web", "date"}, "score": 0.9}]
  ```
- `tavily_api_key` 为空时抛 RuntimeError

### 意图识别

Orchestrator 新增意图判断变量：

```python
needs_web = any(kw in message for kw in ["最新", "实时", "今天新闻", "现在", "刚刚", "突发", "联网", "网上"])
```

### 触发矩阵

| 条件 | 行为 |
|------|------|
| `needs_web == True` | 直接联网搜索（即使有本地结果也追加） |
| `needs_search == True` 且本地为空 | 自动 fallback 联网 |
| `needs_search == True` 且本地有结果 | 仅用本地结果 |
| 都不命中 | 不检索 |

### 来源区分

- 本地搜索结果 sources 增加 `"kind": "local"`
- 网络搜索结果 sources 标记 `"kind": "web"`
- 前端 SourceCards 按 kind 分组渲染，web 用蓝色标签

### 异常处理

- Tavily 请求失败 → thinking 提示"联网搜索失败"，不中断流程
- 配额耗尽 → 同上降级提示

### 配额说明

- Tavily 免费层 1000 次/月
- 仅靠意图关键词隐式触发（未来可扩展为 ChatInput 上的"联网"开关）

---

## Feature 3: 文件上传

### 问题

用户想让 AI 分析一份 PDF 研报或截图中的图表，当前只能手动复制粘贴文字。

### 方案概览

采用**先上传再引用**的两步架构：
1. `POST /api/uploads` — 上传文件、解析内容、返回 attachment ID
2. `POST /api/chat` body 中携带 `attachments: ["id1", "id2"]`

**为什么不用单一 multipart 端点**：
- 上传是一次性请求，chat 是 SSE 流，混合会互相干扰
- 文件可在发消息前上传，前端展示预览
- 大文件超时策略与 chat 不同
- 解析失败可独立重试

### 支持的文件类型

| MIME | 类型 | 解析方式 |
|------|------|----------|
| `text/plain` | 文本 | 直接读取，截断 32k 字符 |
| `text/markdown` | 文本 | 直接读取，截断 32k 字符 |
| `application/pdf` | 文本 | pdfplumber 逐页提取，截断 32k |
| `text/csv` | 文本 | 读为纯文本，截断 32k |
| `image/png` | 图片 | 不解析文本，读为 base64 data URI |
| `image/jpeg` | 图片 | 同上 |
| `image/webp` | 图片 | 同上 |

单文件上限：20MB

### 文件存储

```
memory/uploads/{session_id}/{uuid}.{ext}
memory/uploads/{session_id}/index.json   ← 元数据索引
```

### API 设计

```
POST /api/uploads
  Content-Type: multipart/form-data
  Fields: session_id, files (multiple)
  Response: [
    {
      "id": "abc123",
      "filename": "report.pdf",
      "mime": "application/pdf",
      "size": 123456,
      "kind": "text" | "image",
      "preview_url": "/api/uploads/abc123",
      "extracted_text": "...(仅文本类，截断)"
    }
  ]

GET /api/uploads/{upload_id}
  → 返回原文件（校验归属）
```

### Orchestrator 处理

**文本类附件**：提取的文字拼入 system message：
```
system: "用户上传了以下文件：\n\n【文件1: report.pdf】\n{extracted_text}\n\n..."
```

**图片类附件**：构造 OpenAI Vision 多模态 content array：
```json
{"role": "user", "content": [
    {"type": "text", "text": "用户消息"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
]}
```

**Vision 模型降级**：若当前配置的模型不支持图片（如 DeepSeek），则在 thinking 中提示"当前模型不支持图像，已忽略图片附件"，仅处理文本部分。

### 前端交互

- ChatInput 新增 📎 按钮 + 拖拽上传
- 选中文件后立即上传，显示预览条（图片缩略图 / 文件名 + ❌删除）
- 发送时带上 attachment IDs
- MessageBubble 渲染用户消息中的附件（图片/文件卡片）
- 历史会话加载时从 DB attachments 字段恢复

### 数据库改动

messages 表新增 `attachments TEXT` 列（JSON 格式），存储附件元数据（不含 extracted_text 减小存储）。

### 新增依赖

```toml
"python-multipart>=0.0.9"
"pdfplumber>=0.11"
"pillow>=10"
```

---

## 前端类型变更

### `frontend/lib/types.ts`

```typescript
// 新增
export interface Attachment {
  id: string;
  filename: string;
  mime: string;
  size: number;
  kind: 'text' | 'image';
  preview_url: string;
}

// 修改
export interface Message {
  // ... 现有字段
  attachments?: Attachment[];  // 新增
}

export interface Source {
  // ... 现有字段
  kind?: 'local' | 'web';  // 新增
}
```

---

## SSE 事件流变更

无新增事件类型，现有 `thinking | token | done | session_id` 足够。

Web 搜索过程通过 thinking 事件展示：
```json
{"type": "thinking", "agent": "research", "text": "联网搜索 Tavily..."}
{"type": "thinking", "agent": "research", "text": "网络找到 5 条结果"}
```

---

## 安全考虑

- 文件上传 mime 校验 + PIL 二次验证图片真实类型
- 文件名用 uuid 重命名（规避路径遍历）
- 保存路径 `Path.resolve()` 确认在 uploads_root 内
- Tavily API key 仅服务端使用
- 附件仅所属用户可访问

---

## 性能考虑

- PDF 解析放 `asyncio.to_thread` 避免阻塞事件循环
- 流式 LLM 用 `httpx.AsyncClient` 支持 HTTP/2
- 附件文本截断 32k 字符（约 8k token）防 prompt 爆炸
- 多附件总文本上限 64k 字符

---

## 不在范围内

- 音频/视频文件支持
- 附件 GC（删除 session 时清理文件）— 另起任务
- 前端"联网"开关 toggle — 当前仅关键词隐式触发
- DeepSeek Reasoning 模型的 `reasoning_content` 映射到 thinking 事件
- 移动端适配
