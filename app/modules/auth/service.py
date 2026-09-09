"""Auth 业务用例:注册、登录、查询当前用户信息。

依赖:
- UserRepository:用户读写
- app.common.security.password:密码哈希/校验
- app.common.security.jwt:JWT 签发/解析
- app.common.exceptions.handler.AppException:统一业务异常
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions.handler import AppException
from app.common.security import jwt as jwt_util
from app.common.security import password as pwd_util
from app.config.settings import get_settings
from app.models.user_system import User
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserInfoResponse,
)
from app.modules.user.repository.user_repository import UserRepository


class AuthService:
    """认证业务服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

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
        """登录并签发 JWT。

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

        token = jwt_util.create_access_token(user.id, user.username)
        expires_in = get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
        )

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
