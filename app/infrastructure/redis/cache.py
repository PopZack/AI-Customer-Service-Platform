"""通用 Redis 缓存工具类:JSON 序列化的 key-value 缓存。

本阶段(Phase 12)仅提供工具,不集成进现有 service;
后续阶段(chat 会话缓存、知识库元数据缓存)按需引入。

key 约定:cache:{namespace}:{key}(调用方自行拼接 namespace)
"""
import json
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis


class Cache:
    """Redis JSON 缓存。"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def get(self, key: str, default: Any = None) -> Any:
        """读取缓存,反序列化 JSON;不存在返回 default。"""
        raw = await self.redis.get(key)
        if raw is None:
            return default
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """写入缓存,JSON 序列化,带 TTL(秒)。"""
        await self.redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)

    async def delete(self, key: str) -> int:
        """删除缓存,返回被删 key 数量。"""
        return await self.redis.delete(key)

    async def get_or_set(
        self,
        key: str,
        ttl: int,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        """cache-aside 模式:缓存未命中时调 factory 取值并回填。"""
        cached = await self.get(key, default=None)
        if cached is not None:
            return cached
        value = await factory()
        await self.set(key, value, ttl)
        return value
