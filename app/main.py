"""FastAPI 应用入口。

职责:创建 app、加载配置、初始化日志、注册中间件/异常/路由、健康检查。
本文件不是业务代码,而是整个系统的启动器。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.common.exceptions.handler import register_exception_handlers
from app.common.middleware.request_id import RequestIDMiddleware
from app.config.logging import setup_logging
from app.config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:启动前初始化日志,后续阶段在此初始化/释放数据库、Redis 等连接。"""
    setup_logging()
    # TODO(第 10 阶段):初始化数据库连接池
    # TODO(第 12 阶段):初始化 Redis 连接
    yield
    # TODO:关闭连接


def create_app() -> FastAPI:
    """应用工厂。"""
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        description="企业 AI 客服平台:AI + 人工协同",
    )

    # 中间件(后添加先执行:RequestID 最外层)
    app.add_middleware(RequestIDMiddleware)

    # 全局异常处理
    register_exception_handlers(app)

    # 业务路由:统一挂在 /api/v1 前缀下
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # 顶层健康检查(不走 v1 前缀,供负载均衡/容器探活)
    @app.get("/health", tags=["Health"])
    async def _health():
        return {"status": "ok"}

    return app


# 供 uvicorn 加载:uvicorn app.main:app
app = create_app()
