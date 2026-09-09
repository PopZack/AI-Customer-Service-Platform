"""Redis async 客户端:连接池 + 单例 + 生命周期 + 依赖注入。

镜像 app/infrastructure/database/session.py 的模式:
- 模块级 redis_client 单例(中间件无法用 Depends,直接 import)
- init_redis() / close_redis() 由 lifespan 调用
- get_redis() 作为 FastAPI 依赖

decode_responses=True:所有返回值为 str 而非 bytes,简化业务代码。
"""
from redis.asyncio import ConnectionPool, Redis

from app.config.settings import get_settings

settings = get_settings()


def _build_client() -> Redis | None:
    """根据 REDIS_URL 创建 async Redis 客户端。未配置时返回 None(延迟初始化)。"""
    url = settings.REDIS_URL
    if not url:
        return None
    pool = ConnectionPool.from_url(
        url,
        decode_responses=True,  # 返回 str 而非 bytes
        max_connections=50,
    )
    return Redis(connection_pool=pool)


# 镜像 session.py 的 engine:模块级单例,中间件直接 import
redis_client: Redis | None = _build_client()


async def init_redis() -> None:
    """应用启动时调用:ping 验证连接可用。"""
    if redis_client is None:
        return
    # 验证连接
    await redis_client.ping()


async def close_redis() -> None:
    """应用关闭时调用:释放连接池。"""
    if redis_client is not None:
        await redis_client.aclose()


async def get_redis() -> Redis:
    """FastAPI 依赖:提供 Redis 客户端。

    Raises:
        RuntimeError: REDIS_URL 未配置
    """
    if redis_client is None:
        raise RuntimeError(
            "REDIS_URL 未配置,请在 .env 中设置后重启服务。"
        )
    return redis_client
