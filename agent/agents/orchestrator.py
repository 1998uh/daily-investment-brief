from __future__ import annotations

import json
import datetime
from typing import Any, AsyncGenerator

from agent.config import AgentSettings
from agent.agents.tools import (
    get_daily_brief, tool_search_local, tool_get_user_context,
    tool_add_watch, tool_remove_watch, tool_get_watchlist,
    tool_log_trade, tool_get_trades,
    tool_log_event, tool_get_events,
    tool_run_pipeline,
)


def _sse(type: str, **kwargs) -> dict:
    return {"type": type, **kwargs}


class Orchestrator:
    def __init__(self, settings: AgentSettings, user_id: str):
        self._settings = settings
        self._user_id = user_id

    async def run(
        self,
        message: str,
        history: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Yield SSE event dicts: thinking | token | done."""
        settings = self._settings
        user_id = self._user_id

        # 没有 LLM 配置时降级为简单响应
        if not settings.llm_base_url or not settings.llm_model:
            yield _sse("thinking", agent="orchestrator", text="LLM 未配置，进入简单响应模式")
            yield _sse("token", text="当前未配置 LLM。请在 .env 中设置 BRIEF_BASE_URL / BRIEF_MODEL / BRIEF_API_KEY。")
            yield _sse("done", sources=[])
            return

        # 获取用户上下文
        yield _sse("thinking", agent="orchestrator", text="正在加载用户上下文...")
        user_ctx = await tool_get_user_context(settings, user_id)

        today = datetime.date.today().isoformat()

        # 构建 system prompt
        system_prompt = f"""你是一个专业的投资助手。今天的日期是：{today}

## 重要规则
- 直接用中文 markdown 回答，**不要**输出任何 XML 标签、工具调用语法或占位符（如 <search>、<tool> 等）
- 所有需要的资料已由系统在消息中提前注入，你只需基于这些内容回答
- 如果上下文中没有相关资料，直接说明即可，不要尝试自己发起检索

## 用户个人数据
{user_ctx}"""

        # 构建对话历史
        messages = [{"role": "system", "content": system_prompt}]
        for h in (history or []):
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        # 意图识别：判断是否需要检索
        yield _sse("thinking", agent="orchestrator", text="分析意图...")

        needs_brief = any(kw in message for kw in ["简报", "今天", "每日"])
        needs_search = any(kw in message for kw in ["怎么看", "分析", "观点", "文章", "历史", "检索", "搜索", "涨", "跌", "行情", "市场"])
        needs_memory_write = any(kw in message for kw in ["买了", "卖了", "买入", "卖出", "关注", "记录", "记一下"])
        needs_pipeline = any(kw in message for kw in ["生成简报", "采集", "更新索引"])

        sources = []

        # 简报直读分支（优先于语义检索）
        if needs_brief:
            yield _sse("thinking", agent="research", text=f"读取 {today} 每日简报...")
            brief_content = await get_daily_brief(settings, today)
            if "未找到" not in brief_content:
                messages.append({
                    "role": "system",
                    "content": f"以下是今天（{today}）的每日简报，请基于此回答：\n\n{brief_content}"
                })
                sources.append({"title": f"{today} 每日简报", "date": today})
                yield _sse("thinking", agent="research", text="已加载今日简报")
            else:
                yield _sse("thinking", agent="research", text=brief_content)

        # 语义检索分支
        if needs_search:
            yield _sse("thinking", agent="research", text=f"检索本地文章：{message[:30]}...")
            results = await tool_search_local(settings, message, top_k=5)
            if results:
                context_parts = []
                for r in results:
                    meta = r["metadata"]
                    context_parts.append(
                        f"【{meta.get('author', '未知')}，{meta.get('date', '')}】\n{r['content']}"
                    )
                    sources.append({
                        "title": meta.get("title", ""),
                        "author": meta.get("author", ""),
                        "date": meta.get("date", ""),
                        "url": meta.get("url", ""),
                        "source": meta.get("source", ""),
                    })
                context = "\n\n---\n\n".join(context_parts)
                messages.append({
                    "role": "system",
                    "content": f"以下是检索到的相关文章，请基于这些内容回答：\n\n{context}"
                })
                yield _sse("thinking", agent="research", text=f"找到 {len(results)} 篇相关文章")
            else:
                yield _sse("thinking", agent="research", text="本地未找到相关文章")

        # 记忆写入分支（简单关键词解析，完整解析由 LLM 完成）
        if needs_memory_write:
            yield _sse("thinking", agent="memory", text="解析记忆操作...")

        # Pipeline 分支
        if needs_pipeline:
            yield _sse("thinking", agent="action", text="检测到 pipeline 操作（需前端确认）")

        # 调用 LLM 生成回复（流式）
        yield _sse("thinking", agent="orchestrator", text="生成回复...")
        try:
            from pipeline.llm import chat_completion
            from pipeline.config import get_settings as get_pipeline_settings
            pipeline_settings = get_pipeline_settings()
            response_text = chat_completion(pipeline_settings, messages)
            # 模拟流式：按句子分块 yield token 事件
            for chunk in _split_to_chunks(response_text, size=50):
                yield _sse("token", text=chunk)
        except Exception as exc:
            yield _sse("token", text=f"生成回复时出错：{exc}")

        yield _sse("done", sources=sources)


def _split_to_chunks(text: str, size: int = 50) -> list[str]:
    """将文本按 size 字符分块，模拟流式 token 输出。"""
    return [text[i:i+size] for i in range(0, len(text), size)]
