"""会话模块 Repository。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repository.base import BaseRepository
from app.models.conversation import Conversation, Message


class ConversationRepository(BaseRepository[Conversation]):
    """会话数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Conversation)

    async def list_by_user(self, user_id: int) -> list[Conversation]:
        """按用户查询会话列表。"""
        stmt = select(Conversation).where(Conversation.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MessageRepository(BaseRepository[Message]):
    """消息数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Message)

    async def list_by_conversation(self, conversation_id: int) -> list[Message]:
        """按会话查询消息列表。"""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
