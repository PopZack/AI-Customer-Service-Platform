"""Agent 工具执行器(第 15 阶段 V7)。

工具是"模型能对系统做的事",因此每个工具都必须:
1. **做权限校验** —— 工具参数来自模型输出,而模型可能被用户诱导。查工单必须校验归属。
2. **返回模型能读懂的文本** —— 不要抛异常给模型,把失败原因作为内容返回,让它自行决定下一步。
3. **显式声明副作用** —— 建单 / 转人工会改变业务状态,通过 ToolResult 回传标记,
   由上层决定要不要改会话状态、要不要告知用户。

与 RAG 的关系:`search_knowledge` 直接复用 M1 的 retriever,不重造检索。
"""
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.config import RETRIEVAL_TOP_K
from app.ai.rag.retriever import retrieve
from app.ai.tools.definitions import (
    CREATE_TICKET,
    GET_TICKET,
    GET_USER_PROFILE,
    HANDOFF_TO_HUMAN,
    SEARCH_KNOWLEDGE,
)
from app.common import metrics
from app.models.conversation import Conversation, ConversationStatus, Message
from app.models.ticket import Ticket, TicketMessage, TicketPriority, TicketStatus
from app.models.user_system import User

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """工具执行所需的上下文(由 Agent 在调用时注入)。"""

    session: AsyncSession
    conversation_id: int
    user: User | None = None


@dataclass
class ToolResult:
    """工具执行结果。"""

    content: str  # 回给模型的内容(应为可直接阅读的文本)
    ok: bool = True
    #: 本轮检索是否为空 —— 隐式转人工的判定信号
    retrieval_empty: bool = False
    #: 是否已把会话置为"等待人工"
    handoff_requested: bool = False
    #: 本次调用是否新建了工单
    ticket_created: int | None = None


async def execute_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """按名字分派执行工具。未知工具/参数错误都返回 ok=False 的文本,不抛异常。"""
    metrics.inc("tool_calls_total", tool=name)
    try:
        if name == SEARCH_KNOWLEDGE:
            return await _search_knowledge(ctx, arguments)
        if name == GET_USER_PROFILE:
            return _get_user_profile(ctx)
        if name == GET_TICKET:
            return await _get_ticket(ctx, arguments)
        if name == CREATE_TICKET:
            return await _create_ticket(ctx, arguments)
        if name == HANDOFF_TO_HUMAN:
            return await _handoff_to_human(ctx, arguments)
    except Exception as e:
        logger.exception("工具 %s 执行异常", name)
        return ToolResult(f"工具 {name} 执行失败:{type(e).__name__}: {e}", ok=False)

    logger.warning("模型请求了未定义的工具:%s", name)
    return ToolResult(f"没有名为 {name} 的工具,请使用已提供的工具。", ok=False)


# ── 各工具实现 ──────────────────────────────────────────


async def _search_knowledge(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    if not query:
        return ToolResult("search_knowledge 需要一个非空的 query 参数。", ok=False)

    try:
        top_k = int(args.get("top_k") or RETRIEVAL_TOP_K)
    except (TypeError, ValueError):
        top_k = RETRIEVAL_TOP_K
    top_k = max(1, min(top_k, 20))

    chunks = await retrieve(ctx.session, query, top_k=top_k)
    if not chunks:
        return ToolResult(
            "知识库中没有检索到与该问题相关的内容。可以换一种说法再检索,"
            "或者告知用户当前知识库未覆盖此问题。",
            retrieval_empty=True,
        )

    # 带上 chunk_id,便于日志与前端引用定位
    blocks = [f"[{i}] (来源: {c.file_name}, chunk {c.chunk_id})\n{c.content}" for i, c in enumerate(chunks, 1)]
    return ToolResult("\n\n".join(blocks))


def _get_user_profile(ctx: ToolContext) -> ToolResult:
    user = ctx.user
    if user is None:
        return ToolResult("当前会话没有关联登录用户,无法获取用户资料。", ok=False)
    return ToolResult(
        json.dumps(
            {
                "username": user.username,
                "nickname": user.nickname,
                "email": user.email,
                "phone": user.phone,
                "status": "启用" if user.status == 1 else "禁用",
            },
            ensure_ascii=False,
        )
    )


async def _get_ticket(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    ticket: Ticket | None = None

    raw_id = args.get("ticket_id")
    if raw_id not in (None, "", 0):
        try:
            ticket_id = int(raw_id)
        except (TypeError, ValueError):
            return ToolResult(f"ticket_id 必须是整数,收到 {raw_id!r}。", ok=False)
        ticket = await ctx.session.get(Ticket, ticket_id)
        if ticket is None:
            return ToolResult(f"没有找到 ID 为 {ticket_id} 的工单。", ok=False)
        # 权限校验:工具参数来自模型输出,不能让它越权读别的用户的工单
        if ctx.user is not None and ticket.user_id not in (None, ctx.user.id):
            return ToolResult("该工单不属于当前用户,无权查看。", ok=False)
    else:
        # 未指定则取当前会话关联的工单
        stmt = (
            select(Ticket)
            .where(Ticket.conversation_id == ctx.conversation_id)
            .order_by(Ticket.created_at.desc())
            .limit(1)
        )
        ticket = (await ctx.session.execute(stmt)).scalars().first()
        if ticket is None:
            return ToolResult("当前会话还没有关联的工单。")

    msgs = (
        await ctx.session.execute(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket.id)
            .order_by(TicketMessage.created_at.asc())
            .limit(20)
        )
    ).scalars().all()

    lines = [
        f"工单 #{ticket.id}",
        f"状态:{TicketStatus.TEXT.get(ticket.status, '未知')}",
        f"优先级:{TicketPriority.TEXT.get(ticket.priority, '未知')}",
        f"指派人:{ticket.assigned_user or '尚未指派'}",
    ]
    if msgs:
        lines.append("往来记录:")
        lines.extend(f"  [{m.sender_type}] {m.content}" for m in msgs)
    return ToolResult("\n".join(lines))


async def _create_ticket(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    summary = str(args.get("summary", "")).strip()
    if not summary:
        return ToolResult("create_ticket 需要一个非空的 summary 参数。", ok=False)

    try:
        priority = int(args.get("priority") or TicketPriority.MEDIUM)
    except (TypeError, ValueError):
        priority = TicketPriority.MEDIUM
    if priority not in TicketPriority.TEXT:
        priority = TicketPriority.MEDIUM

    ticket = Ticket(
        conversation_id=ctx.conversation_id,
        user_id=ctx.user.id if ctx.user else None,
        status=TicketStatus.PENDING,
        priority=priority,
    )
    ctx.session.add(ticket)
    await ctx.session.flush()

    ctx.session.add(
        TicketMessage(ticket_id=ticket.id, sender_type="ai", content=summary)
    )
    await ctx.session.commit()

    return ToolResult(
        f"已创建工单 #{ticket.id}(优先级 {TicketPriority.TEXT[priority]},状态 待处理)。"
        f"请把这个工单号告知用户。",
        ticket_created=ticket.id,
    )


async def _handoff_to_human(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """工具入口:转人工。实际动作委托给 request_handoff。"""
    reason = str(args.get("reason", "")).strip() or "AI 无法解决"
    return await request_handoff(ctx, reason)


async def request_handoff(ctx: ToolContext, reason: str) -> ToolResult:
    """执行转人工:置会话状态 + 落 system 消息 + 保证有工单可追。

    公开给两条路径共用:
      - 模型调用 handoff_to_human 工具
      - ChatService 的隐式判定(连续 N 次检索为空)
    两处逻辑必须完全一致,否则「转人工」会出现两种不同的落库形态。
    """
    conv = await ctx.session.get(Conversation, ctx.conversation_id)
    if conv is None:
        return ToolResult("会话不存在,无法转人工。", ok=False)

    if conv.status == ConversationStatus.HUMAN:
        return ToolResult("该会话已经由人工客服接管。", handoff_requested=True)

    # 转人工:若有会话标题就留着,没有则用原因兜底,便于客服列表辨认
    conv.status = ConversationStatus.WAITING_HUMAN
    if not conv.title:
        conv.title = reason[:50]

    # 落一条 system 消息,让对话流里能看到转接动作(用户与客服都能看到)
    ctx.session.add(
        Message(
            conversation_id=ctx.conversation_id,
            sender_type="system",
            content=f"已请求转人工。原因:{reason}",
            message_type="text",
        )
    )

    # 没有工单就顺手建一个,保证转人工一定有责任凭证可追
    existing = (
        await ctx.session.execute(
            select(Ticket).where(Ticket.conversation_id == ctx.conversation_id).limit(1)
        )
    ).scalars().first()
    ticket_id = existing.id if existing else None
    if existing is None:
        ticket = Ticket(
            conversation_id=ctx.conversation_id,
            user_id=ctx.user.id if ctx.user else None,
            status=TicketStatus.PENDING,
            priority=TicketPriority.MEDIUM,
        )
        ctx.session.add(ticket)
        await ctx.session.flush()
        ticket_id = ticket.id
        ctx.session.add(
            TicketMessage(ticket_id=ticket.id, sender_type="system", content=f"转人工原因:{reason}")
        )

    await ctx.session.commit()

    return ToolResult(
        f"已将会话转交人工客服(工单 #{ticket_id})。请告知用户已转接,"
        f"并说明客服会尽快跟进;不要再继续自行作答。",
        handoff_requested=True,
        ticket_created=ticket_id,
    )
