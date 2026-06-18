# Plan E: 对话功能增强实施计划

**对应规格**：`specs/2026-06-18-chat-enhancement.md`  
**预估工作量**：3-4 小时  
**前置条件**：无（不依赖 Plan A-D）

---

## Task 1: 异步流式 LLM 客户端

**文件**：`agent/llm.py`（新建）

创建独立的异步流式 LLM 基础设施：
- 使用 `httpx.AsyncClient` 实现 OpenAI-compatible SSE 流式请求
- 逐 token yield 内容
- 完整的错误处理（HTTP 错误、超时、JSON 解析异常）
- 自定义 `LLMStreamError` 异常类

**验证**：单元测试 mock httpx 响应，确认逐 token 产出。

---

## Task 2: Orchestrator 流式改造

**文件**：`agent/agents/orchestrator.py`

- 删除 `_split_to_chunks` 辅助函数
- LLM 调用块改为 `async for delta in stream_chat_completion(...)`
- 保留 try/except fallback：流式失败 → 降级到 `pipeline.llm.chat_completion` 同步调用
- 确保 SSE 事件格式不变（`type: "token", text: delta`）

**验证**：本地启动 agent server，对话确认打字机效果。

---

## Task 3: Web 搜索工具

**文件**：`agent/agents/tools.py`

- 新增 `tool_search_web()` 函数
- 使用 Tavily SDK，`asyncio.to_thread` 包装
- 返回结构与 `tool_search_local` 对齐（`content`, `metadata`, `score`）
- metadata 包含 `kind: "web"`, `source: "tavily"`

**验证**：手动调用确认 Tavily 返回结构正确。

---

## Task 4: Orchestrator Web 搜索分支

**文件**：`agent/agents/orchestrator.py`

- 添加 `needs_web` 意图识别（关键词匹配）
- 修改搜索分支逻辑：
  - `needs_web` → 调用 `tool_search_web`
  - `needs_search` 且本地为空 → fallback 调用 `tool_search_web`
  - `needs_search` 且本地有结果 → 仅用本地
- 本地结果标记 `kind: "local"`
- Web 搜索异常不中断流程，用 thinking 事件提示

**验证**：对话中发"最新美股行情"触发联网；发"分析XX"只走本地。

---

## Task 5: 文件上传后端

**文件**：`agent/routers/uploads.py`（新建）、`agent/main.py`

- 创建 `/api/uploads` POST 端点（multipart/form-data）
- 文件保存到 `memory/uploads/{session_id}/{uuid}.{ext}`
- 文本类文件解析（pdfplumber for PDF, 直接读取 txt/md/csv）
- 图片类文件读为 base64 data URI
- MIME 白名单校验 + PIL 验证图片
- 路径安全检查
- 注册路由到 `agent/main.py`

**验证**：curl 上传 PDF + PNG，确认返回正确 metadata。

---

## Task 6: Orchestrator 附件处理

**文件**：`agent/agents/orchestrator.py`

- `POST /api/chat` body 新增可选 `attachments` 字段
- 文本类附件：拼入 system message
- 图片类附件：构造 Vision 多模态 content array
- 截断保护（单文件 32k，总计 64k）
- 无 vision 能力模型的降级处理

**验证**：上传 PDF 后对话，确认 AI 能引用文件内容。

---

## Task 7: 数据库 schema 扩展

**文件**：`agent/db.py`

- messages 表新增 `attachments TEXT` 列
- 存储 JSON 格式附件元数据（id, filename, mime, kind）
- chat 历史加载时恢复 attachments

**验证**：上传附件对话 → 刷新页面 → 历史消息正确展示附件。

---

## Task 8: 前端文件上传组件

**文件**：
- `frontend/lib/types.ts` — 新增 Attachment 接口, Source 增加 kind
- `frontend/lib/api.ts` — 新增 `uploads.create()` 方法
- `frontend/components/ChatInput.tsx` — 添加 📎 按钮 + 拖拽上传 + 预览条
- `frontend/hooks/useChat.ts` — sendMessage 支持 attachments 参数

功能：
- 点击 📎 或拖拽触发文件选择
- 上传后显示预览条（缩略图 / 文件名 + ❌删除）
- 发送时将 attachment IDs 附在请求中
- 限制：单文件 20MB，最多 5 个文件

**验证**：前端选文件 → 预览显示 → 发送 → AI 能理解内容。

---

## Task 9: 前端 SourceCards 适配

**文件**：`frontend/components/SourceCards.tsx`

- 按 `kind` 分组：本地来源 / 网络来源
- 本地来源保持现有样式
- 网络来源加蓝色标签 + URL 外链
- MessageBubble 渲染附件卡片

**验证**：联网搜索结果展示蓝色"网络"标签 + 可点击链接。

---

## Task 10: 集成测试与依赖安装

**文件**：`pyproject.toml`、`.env.example`

- 确认 agent extras 包含所有新依赖：
  - `httpx>=0.27`
  - `python-multipart>=0.0.9`
  - `pdfplumber>=0.11`
  - `pillow>=10`
- `.env.example` 添加 `TAVILY_API_KEY=` 说明
- 运行 `pip install -e ".[agent]"` 确认安装无冲突
- E2E 场景测试：
  - 纯文本对话 → 流式输出 ✓
  - "最新" 关键词 → 联网 ✓
  - 上传 PDF + 提问 → AI 引用文件 ✓
  - 上传图片 + 提问 → Vision 模型解读 ✓

---

## 实施顺序建议

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 10(部分)
              ↓
         Task 5 → Task 6 → Task 7
              ↓
         Task 8 → Task 9 → Task 10(完整)
```

**关键路径**：Task 1-2（流式基础设施）是所有后续工作的前提。
Task 3-4（搜索）与 Task 5-7（上传）可并行开发。
Task 8-9（前端）依赖后端就绪。

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| 模型不支持 stream | fallback 同步调用 |
| Tavily 配额耗尽 | 降级提示，不中断 |
| PDF 解析 OOM | asyncio.to_thread + 32k 截断 |
| 大图片 base64 超 LLM context | 压缩到 1024px + 质量 80% |
| 前端拖拽兼容性 | 同时支持点击选择 |
