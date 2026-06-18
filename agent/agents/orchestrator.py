from __future__ import annotations

import json
import datetime
from typing import Any, AsyncGenerator

from agent.config import AgentSettings
from agent.agents.tools import (
    get_daily_brief, tool_search_local, tool_search_web, tool_get_user_context,
    tool_add_watch, tool_remove_watch, tool_get_watchlist,
    tool_log_trade, tool_get_trades,
    tool_log_event, tool_get_events,
    tool_run_pipeline,
)
from agent.llm import stream_chat_completion, LLMStreamError


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
        attachments: list[dict] | None = None,
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

        # 处理附件：文本类拼入 system message，图片类提示不支持
        if attachments:
            text_parts = []
            has_images = False
            for att in attachments:
                if att.get("kind") == "text" and att.get("extracted_text"):
                    text_parts.append(f"【文件: {att.get('filename', '?')}】\n{att['extracted_text']}")
                elif att.get("kind") == "image":
                    has_images = True
            if text_parts:
                file_context = "\n\n---\n\n".join(text_parts)
                messages.append({
                    "role": "system",
                    "content": f"用户上传了以下文件，请基于其内容回答：\n\n{file_context[:64000]}"
                })
                yield _sse("thinking", agent="orchestrator", text=f"已加载 {len(text_parts)} 个文本附件")
            if has_images:
                yield _sse("thinking", agent="orchestrator", text="当前模型不支持图片识别，已忽略图片附件")

        messages.append({"role": "user", "content": message})

        # 意图识别：判断是否需要检索
        yield _sse("thinking", agent="orchestrator", text="分析意图...")

        needs_brief = any(kw in message for kw in ["简报", "今天", "每日"])
        needs_search = any(kw in message for kw in ["怎么看", "分析", "观点", "文章", "历史", "检索", "搜索", "涨", "跌", "行情", "市场"])
        needs_web = any(kw in message for kw in ["最新", "实时", "今天新闻", "现在", "刚刚", "突发", "联网", "网上", "最近消息"])
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
        if needs_search or needs_web:
            # 本地 ChromaDB 检索
            local_results = []
            if needs_search:
                yield _sse("thinking", agent="research", text=f"检索本地文章：{message[:30]}...")
                local_results = await tool_search_local(settings, message, top_k=5)
                if local_results:
                    context_parts = []
                    for r in local_results:
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
                            "kind": "local",
                        })
                    context = "\n\n---\n\n".join(context_parts)
                    messages.append({
                        "role": "system",
                        "content": f"以下是检索到的相关文章，请基于这些内容回答：\n\n{context}"
                    })
                    yield _sse("thinking", agent="research", text=f"本地找到 {len(local_results)} 篇相关文章")
                else:
                    yield _sse("thinking", agent="research", text="本地未找到相关文章")

            # Web 搜索分支：显式联网请求 或 本地无结果时 fallback
            if needs_web or (needs_search and not local_results):
                yield _sse("thinking", agent="research", text="联网搜索 Tavily...")
                try:
                    web_results = await tool_search_web(settings, message, max_results=5)
                    if web_results:
                        web_parts = []
                        for r in web_results:
                            meta = r["metadata"]
                            web_parts.append(
                                f"【{meta.get('title', '')}】({meta.get('url', '')})\n{r['content']}"
                            )
                            sources.append({
                                "title": meta.get("title", ""),
                                "author": meta.get("author", ""),
                                "date": meta.get("date", ""),
                                "url": meta.get("url", ""),
                                "source": "tavily",
                                "kind": "web",
                            })
                        web_context = "\n\n---\n\n".join(web_parts)
                        messages.append({
                            "role": "system",
                            "content": f"以下是联网搜索到的实时信息：\n\n{web_context}"
                        })
                        yield _sse("thinking", agent="research", text=f"网络找到 {len(web_results)} 条结果")
                    else:
                        yield _sse("thinking", agent="research", text="联网搜索无结果")
                except Exception as exc:
                    yield _sse("thinking", agent="research", text=f"联网搜索失败：{exc}")

        # 记忆写入分支（简单关键词解析，完整解析由 LLM 完成）
        if needs_memory_write:
            yield _sse("thinking", agent="memory", text="解析记忆操作...")

        # Pipeline 分支
        if needs_pipeline:
            yield _sse("thinking", agent="action", text="检测到 pipeline 操作（需前端确认）")

        # 调用 LLM 生成回复（真正流式）
        yield _sse("thinking", agent="orchestrator", text="生成回复...")
        try:
            async for delta in stream_chat_completion(settings, messages):
                yield _sse("token", text=delta)
        except LLMStreamError:
            # fallback: 降级到同步 pipeline.llm
            try:
                from pipeline.llm import chat_completion
                from pipeline.config import get_settings as get_pipeline_settings
                pipeline_settings = get_pipeline_settings()
                response_text = chat_completion(pipeline_settings, messages)
                yield _sse("token", text=response_text)
            except Exception as exc:
                yield _sse("token", text=f"生成回复时出错：{exc}")
        except Exception as exc:
            yield _sse("token", text=f"生成回复时出错：{exc}")

        yield _sse("done", sources=sources)
