"""Agent 工具的 function-calling 定义(第 15 阶段 V7)。

这里只放「给模型看的」声明(schema + 描述),具体实现见 executor.py。
拆开的原因是:这段 JSON 直接决定模型会不会正确选工具、参数填得对不对,
值得单独 review 和反复打磨;实现则会频繁改动。

描述用中文写 —— 本项目主要面向中文对话场景,中文描述对国产模型的选择准确率更好。
"""
from typing import Any

# 工具名常量(executor 里按名字分派,避免拼写漂移)
SEARCH_KNOWLEDGE = "search_knowledge"
GET_TICKET = "get_ticket"
CREATE_TICKET = "create_ticket"
HANDOFF_TO_HUMAN = "handoff_to_human"
GET_USER_PROFILE = "get_user_profile"

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": SEARCH_KNOWLEDGE,
            "description": (
                "在企业知识库中检索资料。当需要依据公司政策、产品说明、"
                "操作流程等事实性内容回答时使用。可以多次调用以补充不同方面的信息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或问题,尽量保留用户原话中的关键实体",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回条数,默认 6,取值 1-20",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": GET_TICKET,
            "description": (
                "查询工单的当前状态与往来记录。当用户询问「我之前提的问题怎么样了」"
                "「工单进度」,或需要确认是否已有相关工单时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "工单 ID;不填则返回当前会话关联的工单",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": CREATE_TICKET,
            "description": (
                "创建工单并记录问题摘要。当用户的问题需要人工跟进、"
                "或用户明确要求「登记一下」「提交工单」时使用。"
                "创建后请把工单号告诉用户。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "问题摘要,包含用户诉求与已确认的关键信息(如订单号)",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "优先级:1 低 2 中 3 高。涉及资损、账号安全、投诉时用 3",
                        "enum": [1, 2, 3],
                    },
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": HANDOFF_TO_HUMAN,
            "description": (
                "把会话转交人工客服。适用场景:用户明确要求人工、用户表达强烈不满、"
                "涉及账号安全或资金纠纷、知识库资料无法解决且用户已多次追问。"
                "调用后请告知用户已转接人工,不要再继续作答。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "转人工原因,供客服快速了解上下文",
                    }
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": GET_USER_PROFILE,
            "description": "获取当前用户的资料(账号、昵称、邮箱、联系方式、角色)。需要称呼用户或核对身份时使用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

#: 工具名 → 定义,便于测试与断言
TOOL_NAMES = {t["function"]["name"] for t in TOOL_DEFINITIONS}
