"""会话系统模型: conversation / message。"""
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
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


class ConversationStatus:
    """会话状态机(第 16 阶段 V8)。

        AI ──无法解决──→ WAITING_HUMAN ──客服接管──→ HUMAN ──结束──→ CLOSED
         ↑                                                          │
         └────────────── 用户继续追问(可重新交回 AI)────────────────┘

    - AI:AI 正常服务中(默认态)
    - WAITING_HUMAN:已判定需要人工,等待客服接管(此时用户消息仍会入库,但不再由 AI 回答)
    - HUMAN:客服已接管,由人工回复
    - CLOSED:会话结束

    注意:第 9 阶段该列只定义了「1进行中 / 0已结束」,这里把 1/0 的语义
    收窄为 AI/CLOSED 并新增 2/3。旧数据(1)恰好等于「AI 服务中」,语义兼容。
    """

    CLOSED = 0
    AI = 1
    WAITING_HUMAN = 2
    HUMAN = 3

    TEXT: ClassVar[dict[int, str]] = {
        0: "已结束",
        1: "AI 服务中",
        2: "等待人工",
        3: "人工接管",
    }

    #: 仍处于"AI 该回答"的状态
    AI_ACTIVE = (AI,)
    #: 已交给人工(等待或已接管),AI 不再回答
    HUMAN_SIDE = (WAITING_HUMAN, HUMAN)


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
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="状态机:0已结束 1AI服务中 2等待人工 3人工接管",
    )
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
