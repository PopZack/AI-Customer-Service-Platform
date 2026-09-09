"""数据库会话管理: async engine + async session + 依赖注入。

生产环境使用 PostgreSQL + asyncpg;
本地无 PostgreSQL 时可在 .env 中设 DATABASE_URL=sqlite+aiosqlite:///./dev.db 做临时测试。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import get_settings

settings = get_settings()


def _build_engine():
    """根据 DATABASE_URL 创建 async engine。未配置时返回 None(延迟初始化)。"""
    url = settings.DATABASE_URL
    if not url:
        return None
    # asyncpg / aiosqlite 等 async 驱动
    return create_async_engine(
        url,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine = _build_engine()

# session 工厂(engine 为 None 时为 None,使用时再判断)
async_session_factory: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    if engine is not None
    else None
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖: 提供数据库会话,请求结束自动关闭。"""
    if async_session_factory is None:
        raise RuntimeError(
            "DATABASE_URL 未配置,请在 .env 中设置后重启服务。"
        )
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """应用启动时调用: 建立连接池(不建表,建表由 alembic 负责)。"""
    if engine is None:
        return
    # 验证连接
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """应用关闭时调用: 释放连接池。"""
    if engine is not None:
        await engine.dispose()
