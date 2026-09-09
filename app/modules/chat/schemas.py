"""Chat API 数据结构:会话 CRUD + AI 聊天请求/响应。"""
from datetime import datetime

from pydantic import BaseModel, Field


# ── 会话 ────────────────────────────────────────────────


class ConversationCreateRequest(BaseModel):
    """创建会话请求。"""

    title: str | None = Field(None, max_length=255, description="会话标题(可选)")
    channel: str = Field("web", max_length=50, description="渠道:web/wechat/app")


class ConversationResponse(BaseModel):
    """会话响应。"""

    id: int
    title: str | None = None
    channel: str
    status: int
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """会话列表响应。"""

    items: list[ConversationResponse]
    total: int


# ── 消息 ────────────────────────────────────────────────


class MessageResponse(BaseModel):
    """消息响应。"""

    id: int
    conversation_id: int
    sender_type: str = Field(..., description="user/ai/human/system")
    sender_id: int | None = None
    content: str
    message_type: str | None = None
    token_count: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """消息列表响应。"""

    items: list[MessageResponse]


# ── AI 聊天 ──────────────────────────────────────────────


class ChatRequest(BaseModel):
    """AI 聊天请求(SSE 流式端点的 body)。"""

    conversation_id: int = Field(..., description="目标会话 ID")
    message: str = Field(..., min_length=1, max_length=5000, description="用户消息内容")


class ChatResponse(BaseModel):
    """非流式 AI 聊天响应(预留)。"""

    conversation_id: int
    reply: str
