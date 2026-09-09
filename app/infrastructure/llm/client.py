"""LLM 异步客户端:OpenAI 兼容接口,支持流式输出。

镜像 Redis client 的模式:全局单例 + init/close/get_llm + 依赖注入。
"""
from typing import AsyncGenerator

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionStreamOptionsParam

from app.config.settings import get_settings

settings = get_settings()

_client: AsyncOpenAI | None = None


def _build_client() -> AsyncOpenAI | None:
    """根据配置构建 AsyncOpenAI 客户端。未配置则返回 None(开发阶段可降级)。"""
    if not settings.LLM_API_KEY:
        return None
    kwargs: dict = {"api_key": settings.LLM_API_KEY}
    if settings.LLM_BASE_URL:
        kwargs["base_url"] = settings.LLM_BASE_URL
    return AsyncOpenAI(**kwargs)


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
    resp = await client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=messages,
        temperature=temperature or settings.LLM_TEMPERATURE,
        max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        timeout=settings.LLM_TIMEOUT,
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
    stream = await client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=messages,
        temperature=temperature or settings.LLM_TEMPERATURE,
        max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        timeout=settings.LLM_TIMEOUT,
        stream=True,
        stream_options=stream_options,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
