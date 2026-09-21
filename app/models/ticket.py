"""工单系统模型: ticket / ticket_message。"""
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, BigIntPKMixin


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )


class TicketStatus:
    """工单状态(与 Ticket.status 列取值对应)。"""

    PENDING = 0  # 待处理:AI 转人工后自动建单,尚未指派
    PROCESSING = 1  # 处理中:已指派客服
    DONE = 2  # 已完成
    CLOSED = 3  # 已关闭

    TEXT: ClassVar[dict[int, str]] = {0: "待处理", 1: "处理中", 2: "已完成", 3: "已关闭"}


class TicketPriority:
    """工单优先级。"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3

    TEXT: ClassVar[dict[int, str]] = {1: "低", 2: "中", 3: "高"}


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
    # 第 16 阶段补充:sender_id 只能表达"谁发的",无法区分是用户、AI 自动回复还是客服人工回复。
    # 工单是转人工后的责任凭证,这个区分必须留痕。
    sender_type: Mapped[str] = mapped_column(
        String(20), default="system", nullable=False, comment="发送方类型:user/ai/human/system"
    )
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="发送人ID")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    ticket: Mapped["Ticket"] = relationship(back_populates="messages")
