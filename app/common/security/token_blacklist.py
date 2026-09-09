"""Refresh token 黑名单:基于 Redis 的吊销机制。

封装 refresh 吊销逻辑,避免 AuthService 直接操作 redis.set(...),
符合 design_docs/6-系统架构设计-V1.0.md L660-695 的约束:
「上层可以使用它实现 Session/Cache/Rate Limit/...,
  而不是到处直接操作 redis.set(...)」。

- key: auth:refresh:blacklist:{jti}
- value: "1"(占位)
- TTL: refresh token 剩余寿命(exp - now),过期后 key 自动清理,
  黑名单不无限增长。
"""
from redis.asyncio import Redis

REFRESH_BLACKLIST_PREFIX = "auth:refresh:blacklist"


def _key(jti: str) -> str:
    return f"{REFRESH_BLACKLIST_PREFIX}:{jti}"


class TokenBlacklist:
    """refresh token Redis 黑名单。"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def revoke_refresh(self, jti: str, ttl_seconds: int) -> None:
        """吊销 refresh token(加入黑名单)。

        Args:
            jti: refresh token 的 jti claim
            ttl_seconds: 该 refresh token 剩余寿命(秒);过期后 key 自动清理
        """
        if ttl_seconds <= 0:
            # 已过期的 refresh 无需吊销,直接返回
            return
        await self.redis.set(_key(jti), "1", ex=ttl_seconds)

    async def is_refresh_revoked(self, jti: str) -> bool:
        """检查 refresh token 是否已吊销(在黑名单中)。"""
        return bool(await self.redis.exists(_key(jti)))
