"""SQLAlchemy 模型集合。

导入所有模型文件,使 Base.metadata 能收集到全部表定义,
供 alembic autogenerate 使用。
"""
from app.models.ai_config import ModelConfig, PromptTemplate
from app.models.conversation import Conversation, Message
from app.models.knowledge import (
    Document,
    DocumentChunk,
    KnowledgeBase,
    VectorIndex,
)
from app.models.tenant import Tenant
from app.models.ticket import Ticket, TicketMessage
from app.models.user_system import (
    Permission,
    Role,
    User,
    role_permission,
    user_role,
)

__all__ = [
    # 用户权限
    "User",
    "Role",
    "Permission",
    "user_role",
    "role_permission",
    # 知识库
    "KnowledgeBase",
    "Document",
    "DocumentChunk",
    "VectorIndex",
    # 会话
    "Conversation",
    "Message",
    # AI 配置
    "ModelConfig",
    "PromptTemplate",
    # 工单
    "Ticket",
    "TicketMessage",
    # 租户
    "Tenant",
]
