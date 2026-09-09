"""Auth 路由:注册、登录、当前用户。

所有端点统一返回 ResponseBase[T] 结构。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.common.response.base import ResponseBase, success
from app.models.user_system import User
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserInfoResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter()


@router.post("/register", response_model=ResponseBase[UserInfoResponse])
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ResponseBase[UserInfoResponse]:
    """注册新用户(本阶段完全开放,生产环境请加守卫)。"""
    service = AuthService(db)
    user_info = await service.register(req)
    return success(user_info)


@router.post("/login", response_model=ResponseBase[TokenResponse])
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ResponseBase[TokenResponse]:
    """登录并返回 JWT access token。"""
    service = AuthService(db)
    token = await service.login(req)
    return success(token)


@router.get("/me", response_model=ResponseBase[UserInfoResponse])
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ResponseBase[UserInfoResponse]:
    """获取当前登录用户信息(基于 Bearer token)。"""
    service = AuthService(db)
    user_info = await service.get_user_info(current_user.id)
    return success(user_info)
