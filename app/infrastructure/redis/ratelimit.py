"""限流原语:固定窗口算法(INCR + 首次 EXPIRE)。

原子操作保证多请求并发下的计数准确;首次 INCR 返回 1 时设置 TTL,
后续请求不再重置窗口,窗口到期 key 自动清理。

key 约定:ratelimit:{path}:{ip}
"""
from app.infrastructure.redis.client import redis_client


async def acquire(rate_key: str, max_count: int, window: int) -> tuple[bool, int]:
    """尝试获取一次请求配额。

    Args:
        rate_key: Redis key(如 ratelimit:/api/v1/auth/login:127.0.0.1)
        max_count: 窗口内最大请求数
        window: 窗口大小(秒)

    Returns:
        (allowed, remaining):是否放行 + 剩余配额
    """
    if redis_client is None:
        # fail-open:Redis 未配置时放行(中间件层会记 warning)
        return True, max_count

    count = await redis_client.incr(rate_key)
    if count == 1:
        # 首次请求:设置窗口 TTL
        await redis_client.expire(rate_key, window)
    allowed = count <= max_count
    remaining = max(0, max_count - count)
    return allowed, remaining
