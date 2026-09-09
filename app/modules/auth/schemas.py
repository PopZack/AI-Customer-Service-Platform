"""Auth API 数据结构:注册/登录/Token/当前用户。"""
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册请求。"""

    username: str = Field(..., min_length=3, max_length=50, description="登录账号 3-50 字符")
    password: str = Field(..., min_length=6, max_length=64, description="密码 6-64 字符")


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., description="登录账号")
    password: str = Field(..., description="明文密码")


class TokenResponse(BaseModel):
    """登录成功返回的 JWT token。"""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token,用于续签")
    token_type: str = Field("bearer", description="token 类型,固定 bearer")
    expires_in: int = Field(..., description="access token 有效期(秒)")
    refresh_expires_in: int = Field(..., description="refresh token 有效期(秒)")


class RefreshTokenRequest(BaseModel):
    """刷新 token 请求。"""

    refresh_token: str = Field(..., description="有效的 refresh token")


class LogoutRequest(BaseModel):
    """登出请求。"""

    refresh_token: str = Field(..., description="待吊销的 refresh token")


class LogoutResponse(BaseModel):
    """登出响应。"""

    revoked: bool = Field(..., description="是否成功吊销(已无效的 token 返回 False)")


class UserInfoResponse(BaseModel):
    """用户信息(注册返回、/me 返回)。"""

    id: int
    username: str
    nickname: str | None = None
    email: str | None = None
    phone: str | None = None
    status: int
    tenant_id: int | None = None
    roles: list[str] = Field(default_factory=list, description="角色 code 列表")
