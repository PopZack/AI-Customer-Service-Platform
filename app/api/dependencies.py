"""FastAPI 依赖注入集中管理。

- get_db_session()        数据库会话(第 10 阶段)
- get_redis()            Redis 客户端(第 12 阶段)
- get_current_user()     当前登录用户(第 11 阶段)
- get_current_tenant()   当前租户(多租户阶段)
- 业务 service 实例依赖(后续阶段)
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db_session as _get_db_session


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供数据库会话(自动 commit/rollback)。"""
    async for session in _get_db_session():
        yield session
