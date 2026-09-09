"""API 总路由:聚合各业务模块 router,统一挂 /api/v1 前缀。"""
from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.ticket.router import router as ticket_router
from app.modules.user.router import router as user_router

api_router = APIRouter()

# 各业务模块路由(第 9 阶段为空壳占位,后续阶段填充端点)
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(user_router, prefix="/users", tags=["Users"])
api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
api_router.include_router(knowledge_router, prefix="/knowledge-bases", tags=["Knowledge"])
api_router.include_router(ticket_router, prefix="/tickets", tags=["Tickets"])


@api_router.get("/health", tags=["Health"])
async def health_check():
    """健康检查(v1 前缀下)。"""
    return {"status": "ok"}
