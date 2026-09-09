"""限流中间件:基于固定窗口 + Redis 的请求限流。

- 路由白名单:仅对 settings.RATE_LIMIT_ROUTES 配置的路径生效
- fail-open:Redis 未配置/不可用时放行(记 warning),不阻断主流程
- 超限直接返回 JSONResponse(429, ResponseBase 格式)
  注意:不能用 raise AppException —— Starlette 的 BaseHTTPMiddleware 不会
  把中间件内抛出的异常路由到 app 级 exception_handler,而是吞成 500。
- key:ratelimit:{path}:{ip}

中间件顺序说明:Starlette「后添加先执行」,故 RateLimitMiddleware 应在
RequestIDMiddleware 之后 add,使其位于最外层——超限直接 429,不进入业务层、
不消耗 DB 连接。
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.common.response.base import error
from app.config.settings import get_settings
from app.infrastructure.redis.client import redis_client
from app.infrastructure.redis.ratelimit import acquire

logger = logging.getLogger("app.middleware.rate_limit")

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """固定窗口限流中间件。"""

    async def dispatch(self, request: Request, call_next):
        # 未启用限流 → 直接放行
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Redis 未配置 → fail-open 放行 + warning
        if redis_client is None:
            logger.warning("RATE_LIMIT_ENABLED=true 但 REDIS_URL 未配置,限流跳过(fail-open)")
            return await call_next(request)

        path = request.url.path
        routes = [r.strip() for r in settings.RATE_LIMIT_ROUTES.split(",") if r.strip()]
        if path not in routes:
            # 非限流路由,直接放行
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{path}:{ip}"

        try:
            allowed, remaining = await acquire(
                key,
                settings.RATE_LIMIT_MAX_REQUESTS,
                settings.RATE_LIMIT_WINDOW_SECONDS,
            )
        except Exception as exc:
            # Redis 不可用时 fail-open,避免限流依赖拖垮可用性
            logger.warning("限流计数失败(fail-open):%s", exc)
            return await call_next(request)

        if not allowed:
            # 超限:直接返回 429(不能用 raise,见模块 docstring)
            return JSONResponse(
                status_code=429,
                content=error(429, "请求过于频繁,请稍后再试").model_dump(),
                headers={
                    "X-RateLimit-Limit": str(settings.RATE_LIMIT_MAX_REQUESTS),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS),
                },
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
