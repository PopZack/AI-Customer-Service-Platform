"""Chat API 数据结构:会话 CRUD + AI 聊天请求/响应。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    status_text: str | None = Field(
        None, description="状态机文字:AI服务中 / 等待人工 / 人工接管 / 已结束"
    )
    created_at: datetime

    # Pydantic V2 写法。V1 的 class Config 已弃用,V3 会失效。
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, conv) -> "ConversationResponse":
        """由 ORM 对象构造,顺带补上状态文字(前端直接可显示)。"""
        from app.models.conversation import ConversationStatus

        resp = cls.model_validate(conv)
        resp.status_text = ConversationStatus.TEXT.get(conv.status, "未知")
        return resp


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

    # Pydantic V2 写法。V1 的 class Config 已弃用,V3 会失效。
    model_config = ConfigDict(from_attributes=True)


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


# ── 转人工(第 16 阶段)────────────────────────────────


class HandoffRequest(BaseModel):
    """显式转人工请求。"""

    reason: str | None = Field(None, max_length=255, description="转人工原因(可选)")


class HandoffResponse(BaseModel):
    """转人工结果。"""

    conversation_id: int
    status: int = Field(..., description="会话状态机:2等待人工 3人工接管")
    status_text: str
    ticket_id: int | None = Field(None, description="关联工单 ID(转人工时自动创建)")


class HandoffSignalResponse(BaseModel):
    """转人工判定信号(调试用)。"""

    conversation_id: int
    status: int
    status_text: str
    empty_retrieval_count: int = Field(..., description="当前连续未检索到资料的次数")
    threshold: int = Field(..., description="触发隐式转人工的阈值")
