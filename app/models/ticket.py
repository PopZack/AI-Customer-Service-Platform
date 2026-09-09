"""工单系统模型: ticket / ticket_message。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, BigIntPKMixin


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )


# ── 工单 ────────────────────────────────────────────────
class Ticket(Base, BigIntPKMixin):
    """工单表。"""

    __tablename__ = "ticket"

    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("conversation.id", ondelete="SET NULL"), nullable=True, comment="关联会话"
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, comment="提交用户"
    )
    assigned_user: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, comment="指派客服"
    )
    status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False, comment="状态:0待处理 1处理中 2已完成 3已关闭")
    priority: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False, comment="优先级:1低 2中 3高")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


# ── 工单消息 ────────────────────────────────────────────
class TicketMessage(Base, BigIntPKMixin):
    """工单消息表。"""

    __tablename__ = "ticket_message"

    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, comment="所属工单"
    )
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="发送人ID")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    ticket: Mapped["Ticket"] = relationship(back_populates="messages")
