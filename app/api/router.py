"""API 总路由:聚合各业务模块 router,统一挂 /api/v1 前缀。"""
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_redis
from app.common.exceptions.handler import AppException
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import chat_router as chat_sse_router
from app.modules.chat.router import conversations_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.ticket.router import router as ticket_router
from app.modules.user.router import router as user_router

api_router = APIRouter()

# 各业务模块路由(第 9 阶段为空壳占位,第 13 阶段填充 Chat 端点)
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(user_router, prefix="/users", tags=["Users"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(chat_sse_router, prefix="/chat", tags=["Chat"])
api_router.include_router(knowledge_router, prefix="/knowledge-bases", tags=["Knowledge"])
api_router.include_router(ticket_router, prefix="/tickets", tags=["Tickets"])


@api_router.get("/health", tags=["Health"])
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
):
    """健康检查(readiness 探针):数据库 + Redis 连通性。

    与顶层 /health(liveness,进程存活)分工:
    - 顶层 /health:进程活,不查依赖,供 liveness probe
    - v1 /health:依赖就绪,供 readiness probe
    """
    await db.execute(text("SELECT 1"))
    try:
        await redis.ping()
    except Exception:
        raise AppException(503, "Redis 不可用", http_status=503)
    return {"status": "ok", "database": "connected", "redis": "connected"}
