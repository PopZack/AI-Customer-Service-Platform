"""Auth 路由:注册、登录、刷新、登出、当前用户。

所有端点统一返回 ResponseBase[T] 结构。
"""
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, get_redis
from app.common.response.base import ResponseBase, success
from app.models.user_system import User
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshTokenRequest,
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
    redis: Redis = Depends(get_redis),
) -> ResponseBase[TokenResponse]:
    """登录并返回 access + refresh token。"""
    service = AuthService(db, redis)
    token = await service.login(req)
    return success(token)


@router.post("/refresh", response_model=ResponseBase[TokenResponse])
async def refresh(
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ResponseBase[TokenResponse]:
    """用 refresh token 续签,轮换吊销旧 refresh 并签发新双 token。"""
    service = AuthService(db, redis)
    token = await service.refresh(req)
    return success(token)


@router.post("/logout", response_model=ResponseBase[LogoutResponse])
async def logout(
    req: LogoutRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ResponseBase[LogoutResponse]:
    """登出:吊销当前 refresh token(幂等)。"""
    service = AuthService(db, redis)
    result = await service.logout(req)
    return success(result)


@router.get("/me", response_model=ResponseBase[UserInfoResponse])
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ResponseBase[UserInfoResponse]:
    """获取当前登录用户信息(基于 Bearer token)。"""
    service = AuthService(db)
    user_info = await service.get_user_info(current_user.id)
    return success(user_info)
