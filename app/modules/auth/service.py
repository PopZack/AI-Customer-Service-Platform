"""Auth 业务用例:注册、登录、刷新、登出、查询当前用户信息。

依赖:
- UserRepository:用户读写
- app.common.security.password:密码哈希/校验
- app.common.security.jwt:JWT 签发/解析(access + refresh)
- app.common.security.token_blacklist:refresh token Redis 黑名单
- app.common.exceptions.handler.AppException:统一业务异常
"""
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions.handler import AppException
from app.common.security import jwt as jwt_util
from app.common.security import password as pwd_util
from app.common.security.token_blacklist import TokenBlacklist
from app.config.settings import get_settings
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
from app.modules.user.repository.user_repository import UserRepository


class AuthService:
    """认证业务服务。"""

    def __init__(self, session: AsyncSession, redis: Redis | None = None):
        self.session = session
        self.user_repo = UserRepository(session)
        self.redis = redis
        self.blacklist = TokenBlacklist(redis) if redis else None

    async def register(self, req: RegisterRequest) -> UserInfoResponse:
        """注册新用户。

        - 用户名已存在抛 AppException(400)
        - 密码用 bcrypt 哈希
        - 默认 status=1 启用,tenant_id 为 None(后续绑租户)
        """
        existing = await self.user_repo.get_by_username(req.username)
        if existing is not None:
            raise AppException(400, "用户名已存在")

        hashed = pwd_util.hash_password(req.password)
        user = await self.user_repo.create(
            username=req.username,
            password_hash=hashed,
            status=1,
        )
        # 新建用户无角色
        return self._to_user_info(user, roles=[])

    async def login(self, req: LoginRequest) -> TokenResponse:
        """登录并签发 access + refresh token。

        - 用户不存在 / 密码错误都返回相同消息(防爆破)
        - 账号被禁用单独返回 403
        """
        user = await self.user_repo.get_by_username(req.username)
        if user is None:
            raise AppException(401, "用户名或密码错误")

        if not pwd_util.verify_password(req.password, user.password_hash):
            raise AppException(401, "用户名或密码错误")

        if user.status == 0:
            raise AppException(403, "账号已被禁用")

        settings = get_settings()
        access_token = jwt_util.create_access_token(user.id, user.username)
        refresh_token, _jti = jwt_util.create_refresh_token(user.id, user.username)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_expires_in=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

    async def refresh(self, req: RefreshTokenRequest) -> TokenResponse:
        """用 refresh token 续签,轮换吊销旧 refresh 并签发新双 token。

        流程:
        1. 解析 refresh token(过期/无效抛 401)
        2. 校验 type == "refresh"
        3. 查黑名单(jti 已吊销抛 401)
        4. 轮换:立即吊销旧 refresh(TTL=剩余寿命)
        5. 查库确认用户仍存在且未禁用
        6. 签发新 access + 新 refresh(新 jti)
        """
        if self.blacklist is None:
            raise AppException(503, "Redis 不可用,无法刷新 token", http_status=503)

        payload = jwt_util.decode_refresh_token(req.refresh_token)

        if payload.get("type") != "refresh":
            raise AppException(401, "token 类型错误")

        jti = payload.get("jti")
        if not jti:
            raise AppException(401, "token 载荷异常")

        if await self.blacklist.is_refresh_revoked(jti):
            raise AppException(401, "refresh token 已失效")

        # 轮换:立即吊销旧 refresh(TTL=剩余寿命,过期后 key 自动清理)
        exp_ts = payload.get("exp")
        if exp_ts is not None:
            ttl = int(exp_ts - datetime.now(timezone.utc).timestamp())
            await self.blacklist.revoke_refresh(jti, ttl_seconds=ttl)

        # 查库确认用户仍存在且未禁用
        try:
            user_id = int(payload["sub"])
        except (KeyError, ValueError, TypeError):
            raise AppException(401, "token 载荷异常")

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise AppException(401, "用户不存在或已被删除")
        if user.status == 0:
            raise AppException(403, "账号已被禁用")

        settings = get_settings()
        new_access = jwt_util.create_access_token(user.id, user.username)
        new_refresh, _new_jti = jwt_util.create_refresh_token(user.id, user.username)
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_expires_in=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

    async def logout(self, req: LogoutRequest) -> LogoutResponse:
        """登出:吊销当前 refresh token(幂等)。

        - 解码失败(过期/无效/类型错)→ revoked=False(token 已无效,无需吊销)
        - 解码成功 → 加入黑名单(TTL=剩余寿命)→ revoked=True
        """
        if self.blacklist is None:
            raise AppException(503, "Redis 不可用,无法登出", http_status=503)

        try:
            payload = jwt_util.decode_refresh_token(req.refresh_token)
        except AppException:
            # 已过期/无效,无需吊销;不暴露 token 状态
            return LogoutResponse(revoked=False)

        if payload.get("type") != "refresh":
            return LogoutResponse(revoked=False)

        jti = payload.get("jti")
        if not jti:
            return LogoutResponse(revoked=False)

        exp_ts = payload.get("exp")
        ttl = (
            int(exp_ts - datetime.now(timezone.utc).timestamp())
            if exp_ts is not None
            else 0
        )
        await self.blacklist.revoke_refresh(jti, ttl_seconds=ttl)
        return LogoutResponse(revoked=True)

    async def get_user_info(self, user_id: int) -> UserInfoResponse:
        """按 user_id 查询用户信息(含角色 code 列表)。

        - 用户不存在抛 AppException(404)
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise AppException(404, "用户不存在")

        # 触发懒加载:确保 roles 已加载
        await self.session.refresh(user, ["roles"])
        role_codes = [r.code for r in user.roles]
        return self._to_user_info(user, roles=role_codes)

    @staticmethod
    def _to_user_info(user: User, roles: list[str]) -> UserInfoResponse:
        """User ORM 实例 → UserInfoResponse schema。"""
        return UserInfoResponse(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            phone=user.phone,
            status=user.status,
            tenant_id=user.tenant_id,
            roles=roles,
        )
