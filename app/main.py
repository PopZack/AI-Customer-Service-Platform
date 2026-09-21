"""FastAPI 应用入口。

职责:创建 app、加载配置、初始化日志、注册中间件/异常/路由、健康检查。
本文件不是业务代码,而是整个系统的启动器。
"""
# 必须放在所有业务 import 之前:onnxruntime / OpenBLAS 的线程栈分配依赖这两个变量,
# 且只在 numpy 首次导入前设置才生效(否则报 "OpenBLAS error: Memory allocation
# still failed after 10 retries")。embedding 客户端里也设了一次,这里是双保险。
import os as _os

_os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
_os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.common.exceptions.handler import register_exception_handlers
from app.common.middleware.rate_limit import RateLimitMiddleware
from app.common.middleware.request_id import RequestIDMiddleware
from app.config.logging import setup_logging
from app.config.settings import get_settings
from app.infrastructure.database import close_db, init_db
from app.infrastructure.embedding import close_embedding, init_embedding
from app.infrastructure.llm import close_llm, init_llm
from app.infrastructure.redis import close_redis, init_redis
from app.tasks.document_tasks import (
    process_document_with_retry,
    recover_stuck_document_ids,
)

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:启动前初始化日志/数据库/Redis/LLM/embedding,关闭时释放资源。"""
    setup_logging()
    # 第 10 阶段:初始化数据库连接池
    await init_db()
    # 第 12 阶段:初始化 Redis 连接池
    await init_redis()
    # 第 13 阶段:初始化 LLM 客户端
    await init_llm()
    # 第 14 阶段:预热本地 embedding 模型(首次含模型下载;失败降级,不阻塞启动)
    if not await init_embedding():
        logger.warning("embedding 模型加载失败,知识库向量检索将不可用(关键词检索仍可工作)")
    # Phase 17 精简决策的补强:BackgroundTasks 随进程死亡,启动时恢复被打断的文档任务。
    # 恢复任务丢进事件循环即可 —— 没有用 BackgroundTasks 是因为这里已不在请求作用域内。
    stuck_ids = await recover_stuck_document_ids()
    for doc_id in stuck_ids:
        asyncio.create_task(process_document_with_retry(doc_id))
    if stuck_ids:
        logger.warning("启动恢复:%s 个因重启而中断的文档索引任务已重新入队 %s", len(stuck_ids), stuck_ids)
    yield
    # 释放资源(先关应用层依赖,再关 DB)
    await close_embedding()
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

    # Prometheus 文本格式的进程内计数器(Phase 20 精简版监控)。
    # 抓取端直接配这个路径;要接完整监控系统时无需改业务代码。
    from fastapi import Response

    from app.common.metrics import render

    @app.get("/metrics", tags=["Health"], include_in_schema=False)
    async def _metrics():
        return Response(content=render(), media_type="text/plain; version=0.0.4; charset=utf-8")

    # 静态演示页(第 14 阶段 M1)。目录不存在时跳过,不影响 API 启动。
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def _index():
            """根路径直接跳到演示页,省得手敲路径。"""
            return RedirectResponse("/static/index.html")

    return app


# 供 uvicorn 加载:uvicorn app.main:app
app = create_app()
