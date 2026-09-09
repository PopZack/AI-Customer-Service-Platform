"""JWT 工具:签发与解析 access token。

使用 PyJWT(活跃维护),不使用 python-jose(已停滞)。
载荷采用标准 claim: sub(username)、iat、exp。
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.common.exceptions.handler import AppException
from app.config.settings import get_settings


def create_access_token(
    subject: int,
    username: str,
    expires_minutes: int | None = None,
) -> str:
    """签发 JWT access token。

    Args:
        subject: 用户 ID(作为 sub claim)
        username: 用户名(方便日志/调试)
        expires_minutes: 过期分钟数;None 时读 settings.ACCESS_TOKEN_EXPIRE_MINUTES

    Returns:
        编码后的 JWT 字符串(eyJhbGci...)
    """
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),  # JWT 规范要求 sub 是字符串
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """解析 JWT access token,返回载荷。

    Args:
        token: JWT 字符串

    Returns:
        载荷字典(含 sub/username/iat/exp)

    Raises:
        AppException(401, "token 已过期"): token 过期
        AppException(401, "token 无效"): 签名错/格式错/未通过校验
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except ExpiredSignatureError:
        raise AppException(401, "token 已过期")
    except InvalidTokenError:
        raise AppException(401, "token 无效")
