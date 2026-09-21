"""Ticket API 数据结构:工单列表/详情、指派、人工回复、关闭。

注意:工单表按设计文档就是最小结构(无 title / description),
问题摘要存在**首条 ticket_message** 里,因此列表接口会带一个 summary 字段,
由服务层取首条消息的内容填充 —— 单看 ticket 表无法知道"这单是什么问题"。
"""
from datetime import datetime

from pydantic import BaseModel, Field

# ── 工单 ────────────────────────────────────────────────


class TicketResponse(BaseModel):
    """工单响应。"""

    id: int
    conversation_id: int | None = None
    user_id: int | None = None
    assigned_user: int | None = None
    status: int
    status_text: str | None = None
    priority: int
    priority_text: str | None = None
    summary: str | None = Field(None, description="首条消息摘要(工单表本身无标题字段)")
    created_at: datetime

    class Config:
        from_attributes = True


class TicketMessageResponse(BaseModel):
    """工单消息响应。"""

    id: int
    ticket_id: int
    sender_type: str = Field(..., description="user/ai/human/system")
    sender_id: int | None = None
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class TicketDetailResponse(TicketResponse):
    """工单详情(含往来记录)。"""

    messages: list[TicketMessageResponse] = Field(default_factory=list)


class TicketListResponse(BaseModel):
    """工单列表响应。"""

    items: list[TicketResponse]
    total: int


# ── 操作 ────────────────────────────────────────────────


class TicketAssignRequest(BaseModel):
    """指派工单请求。"""

    agent_id: int | None = Field(
        None, description="客服用户 ID;不传表示「认领给自己」"
    )


class TicketReplyRequest(BaseModel):
    """人工回复请求。"""

    content: str = Field(..., min_length=1, max_length=5000, description="回复内容")


class TicketCloseRequest(BaseModel):
    """关单请求。"""

    resolution: str | None = Field(None, max_length=500, description="处理结论(可选)")
