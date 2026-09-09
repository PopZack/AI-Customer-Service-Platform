"""会话系统模型: conversation / message。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, BigIntPKMixin


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )


# ── 会话 ────────────────────────────────────────────────
class Conversation(Base, BigIntPKMixin):
    """会话表。"""

    __tablename__ = "conversation"

    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.id", ondelete="SET NULL"), nullable=True, comment="所属租户"
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, comment="发起用户"
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="会话标题")
    channel: Mapped[str] = mapped_column(String(50), default="web", nullable=False, comment="渠道:web/wechat/app/email")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False, comment="状态:1进行中 0已结束")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


# ── 消息 ────────────────────────────────────────────────
class Message(Base, BigIntPKMixin):
    """消息表(数据量最大的表)。"""

    __tablename__ = "message"

    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False, comment="所属会话"
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="发送方类型:user/ai/human/system")
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="发送方ID")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    message_type: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="消息类型:text/image/file")
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="token 数")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
