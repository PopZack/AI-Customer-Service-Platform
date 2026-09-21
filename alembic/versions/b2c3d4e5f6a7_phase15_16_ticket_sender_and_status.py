"""phase15-16: ticket_message.sender_type, conversation status semantics

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-09-20

变更内容:
1. ticket_message 增加 sender_type
   原表只有 sender_id,无法区分「用户 / AI 自动回复 / 客服人工回复」。
   工单是转人工之后的责任凭证,这个区分必须留痕,否则排查纠纷时无法还原对话。
   存量行统一填 'system'(语义:来源不明的历史数据)。
2. conversation.status 的列注释更新为状态机语义
   第 9 阶段只定义了「1进行中 / 0已结束」;第 16 阶段扩展为
   0已结束 / 1AI服务中 / 2等待人工 / 3人工接管。
   旧值 1 恰好等于「AI 服务中」,语义兼容,**不需要数据迁移**。
   仅更新注释,让数据库自描述。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | Sequence[str] | None = 'a1f2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. 工单消息发送方类型 ──
    op.execute(
        "ALTER TABLE ticket_message "
        "ADD COLUMN IF NOT EXISTS sender_type varchar(20) NOT NULL DEFAULT 'system'"
    )
    op.execute(
        "COMMENT ON COLUMN ticket_message.sender_type IS "
        "'发送方类型:user/ai/human/system'"
    )
    # 存量行已由 DEFAULT 填好,这里收回默认值,强制后续插入显式指定
    op.execute("ALTER TABLE ticket_message ALTER COLUMN sender_type DROP DEFAULT")

    # ── 2. 会话状态机注释 ──
    op.alter_column(
        "conversation",
        "status",
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
        comment="状态机:0已结束 1AI服务中 2等待人工 3人工接管",
    )


def downgrade() -> None:
    op.alter_column(
        "conversation",
        "status",
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
        comment="状态:1进行中 0已结束",
    )
    op.execute("ALTER TABLE ticket_message DROP COLUMN IF EXISTS sender_type")
