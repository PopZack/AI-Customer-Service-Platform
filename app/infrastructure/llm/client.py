"""LLM 异步客户端:OpenAI 兼容接口,支持流式输出。

镜像 Redis client 的模式:全局单例 + init/close/get_llm + 依赖注入。

Phase 20 加固:
- 重试交给 openai SDK 的内建机制(max_retries 可配):它对连接错误、
  408/429/5xx 做指数退避,自己再包一层纯属重复。
- **fallback 模型**:主模型在 SDK 重试耗尽后仍失败,且配置了
  LLM_FALLBACK_MODEL 时,换备用模型再试一次。fallback 只发生在
  **请求建立阶段**(create 调用返回前),流已开始后不再换模型 ——
  中途换模型等于把前半段回答作废,用户看到的是跳变,不如直接报错。
"""
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionStreamOptionsParam,
)

from app.common import metrics
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_client: AsyncOpenAI | None = None


@dataclass
class ToolCallDelta:
    """流式返回中工具调用的一个增量片段。

    OpenAI 兼容接口把一次工具调用拆成多个 chunk 陆续下发:
    id 与函数名通常只在第一个 chunk 出现,arguments 是被切成多段的 JSON 字符串。
    所以调用方必须**按 index 累积**,不能指望单个 chunk 拿到完整信息。
    """

    index: int
    id: str | None = None
    name: str | None = None
    arguments: str | None = None


@dataclass
class StreamChunk:
    """流式响应的一块(已抹平各厂商差异)。"""

    content: str | None = None
    tool_call: ToolCallDelta | None = None
    finish_reason: str | None = None


def _build_client() -> AsyncOpenAI | None:
    """根据配置构建 AsyncOpenAI 客户端。未配置则返回 None(开发阶段可降级)。"""
    if not settings.LLM_API_KEY:
        return None
    kwargs: dict = {
        "api_key": settings.LLM_API_KEY,
        # SDK 内建重试:连接错误、408/409/429、>=500 指数退避。显式声明便于配置。
        "max_retries": settings.LLM_MAX_RETRIES,
    }
    if settings.LLM_BASE_URL:
        kwargs["base_url"] = settings.LLM_BASE_URL
    return AsyncOpenAI(**kwargs)


async def _create_with_fallback(client: AsyncOpenAI, kwargs: dict[str, Any]):
    """发起一次 create;主模型重试耗尽仍失败且配置了备用模型时,换模型再试。

    只覆盖**请求建立阶段**。对流式调用,create 返回时流尚未开始消费,
    在这里换模型是安全的;流中途的失败不重试(见模块 docstring)。
    """
    try:
        return await client.chat.completions.create(**kwargs)
    except Exception as primary_err:
        fallback = settings.LLM_FALLBACK_MODEL
        if not fallback or fallback == kwargs.get("model"):
            raise
        metrics.inc("llm_fallback_total", model=fallback)
        logger.warning(
            "主模型 %s 失败(%s),切换备用模型 %s 重试",
            kwargs.get("model"), type(primary_err).__name__, fallback,
        )
        fb_kwargs = {**kwargs, "model": fallback}
        return await client.chat.completions.create(**fb_kwargs)


async def init_llm() -> None:
    """启动时初始化 LLM 客户端。"""
    global _client
    _client = _build_client()


async def close_llm() -> None:
    """关闭时释放资源。"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def get_llm() -> AsyncOpenAI:
    """依赖注入用:获取全局 LLM 客户端,未配置则抛异常。"""
    if _client is None:
        raise RuntimeError(
            "LLM 未配置,请在 .env 中设置 LLM_API_KEY 和 LLM_BASE_URL 后重启服务。"
        )
    return _client


def is_llm_available() -> bool:
    """运行时判断 LLM 是否可用(无需 await)。"""
    return _client is not None


# ── 高层封装 ────────────────────────────────────────────


async def chat_non_stream(
    messages: list[ChatCompletionMessageParam],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """非流式聊天:一次性返回完整文本。"""
    client = await get_llm()
    resp = await _create_with_fallback(
        client,
        {
            "model": model or settings.LLM_MODEL,
            "messages": messages,
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
            "timeout": settings.LLM_TIMEOUT,
        },
    )
    return resp.choices[0].message.content or ""


async def chat_stream(
    messages: list[ChatCompletionMessageParam],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """流式聊天:逐 chunk yield 文本增量。"""
    client = await get_llm()
    stream_options: ChatCompletionStreamOptionsParam = {"include_usage": False}
    stream = await _create_with_fallback(
        client,
        {
            "model": model or settings.LLM_MODEL,
            "messages": messages,
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
            "timeout": settings.LLM_TIMEOUT,
            "stream": True,
            "stream_options": stream_options,
        },
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def chat_stream_with_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[StreamChunk, None]:
    """流式聊天,支持工具调用。逐块 yield StreamChunk。

    为什么用流式而不是非流式做工具轮:非流式要等整轮生成完才返回,
    多轮工具调用会让用户干等几十秒。流式下模型开口的思考文字可以先推给用户,
    工具调用增量则按 index 累积到完整再执行。
    """
    client = await get_llm()
    stream_options: ChatCompletionStreamOptionsParam = {"include_usage": False}
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature or settings.LLM_TEMPERATURE,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "timeout": settings.LLM_TIMEOUT,
        "stream": True,
        "stream_options": stream_options,
    }
    if tools:
        kwargs["tools"] = tools
        # 明确要求"由模型自行决定是否调用",避免部分厂商默认强制调用工具
        kwargs["tool_choice"] = "auto"

    stream = await _create_with_fallback(client, kwargs)

    async for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        if delta.content:
            yield StreamChunk(content=delta.content)

        for tc in delta.tool_calls or []:
            yield StreamChunk(
                tool_call=ToolCallDelta(
                    index=tc.index,
                    id=tc.id,
                    name=tc.function.name if tc.function else None,
                    arguments=tc.function.arguments if tc.function else None,
                )
            )

        if choice.finish_reason:
            yield StreamChunk(finish_reason=choice.finish_reason)
