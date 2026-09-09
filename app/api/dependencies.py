"""FastAPI 依赖注入集中管理。

- get_db_session()        数据库会话(第 10 阶段)
- get_redis()             Redis 客户端(第 12 阶段已实现)
- get_current_user()      当前登录用户(第 11 阶段)
- get_current_tenant()    当前租户(多租户阶段)
- 业务 service 实例依赖(后续阶段)
"""
from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions.handler import AppException
from app.common.security.jwt import decode_access_token
from app.infrastructure.database.session import get_db_session as _get_db_session
from app.infrastructure.redis.client import get_redis as _get_redis
from app.models.user_system import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供数据库会话(自动 commit/rollback)。"""
    async for session in _get_db_session():
        yield session


async def get_redis() -> Redis:
    """提供 Redis 客户端(单例,不随请求关闭连接)。"""
    return await _get_redis()


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """从 Authorization: Bearer <token> 解析当前用户。

    流程:
    1. 校验 Authorization 头存在且 scheme 是 bearer
    2. 解析 JWT 拿到 sub(user_id)
    3. 查库确认用户仍存在且未禁用

    Raises:
        AppException(401, "未提供认证 token"): 缺 Authorization 头
        AppException(401, "token 已过期"/"token 无效"): JWT 解析失败
        AppException(401, "用户不存在或已被删除"): user_id 在库中查不到
        AppException(403, "账号已被禁用"): status=0
    """
    if creds is None or not creds.credentials:
        raise AppException(401, "未提供认证 token")

    # 校验 scheme 是 bearer(HTTPBearer 已基本保证,这里二次防御)
    if creds.scheme.lower() != "bearer":
        raise AppException(401, "认证方案错误,只支持 Bearer")

    payload = decode_access_token(creds.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise AppException(401, "token 载荷异常")

    user = await db.get(User, user_id)
    if user is None:
        raise AppException(401, "用户不存在或已被删除")

    if user.status == 0:
        raise AppException(403, "账号已被禁用")

    return user
