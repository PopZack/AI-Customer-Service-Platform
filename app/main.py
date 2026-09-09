"""FastAPI 应用入口。

职责:创建 app、加载配置、初始化日志、注册中间件/异常/路由、健康检查。
本文件不是业务代码,而是整个系统的启动器。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.common.exceptions.handler import register_exception_handlers
from app.common.middleware.rate_limit import RateLimitMiddleware
from app.common.middleware.request_id import RequestIDMiddleware
from app.config.logging import setup_logging
from app.config.settings import get_settings
from app.infrastructure.database import close_db, init_db
from app.infrastructure.llm import close_llm, init_llm
from app.infrastructure.redis import close_redis, init_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:启动前初始化日志/数据库/Redis,关闭时释放资源。"""
    setup_logging()
    # 第 10 阶段:初始化数据库连接池
    await init_db()
    # 第 12 阶段:初始化 Redis 连接池
    await init_redis()
    # 第 13 阶段:初始化 LLM 客户端
    await init_llm()
    yield
    # 释放资源(先关应用层依赖,再关 DB)
    await close_llm()
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    """应用工厂。"""
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        description="企业 AI 客服平台:AI + 人工协同",
    )

    # 中间件(Starlette「后添加先执行」:RateLimit 在 RequestID 之后 add → 最外层,
    # 超限直接 429,不进入业务层、不消耗 DB 连接)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # 全局异常处理
    register_exception_handlers(app)

    # 业务路由:统一挂在 /api/v1 前缀下
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # 顶层健康检查(liveness 探针:进程存活,不查依赖)
    # 与 v1 /health(readiness:查依赖)分工,供 k8s 探针分别配置
    @app.get("/health", tags=["Health"])
    async def _health():
        return {"status": "ok"}

    return app


# 供 uvicorn 加载:uvicorn app.main:app
app = create_app()
