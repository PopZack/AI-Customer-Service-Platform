"""用户模块 Repository。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repository.base import BaseRepository
from app.models.user_system import User


class UserRepository(BaseRepository[User]):
    """用户数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> User | None:
        """按用户名查询。"""
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
