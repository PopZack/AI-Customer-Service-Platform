# 《企业 AI 客服平台》第二阶段：领域模型设计 V1.0

> 前文：《企业 AI 客服平台》PRD V1.0

## 核心问题只有一个

> **系统里到底有哪些业务对象，它们之间是什么关系？**

我们的系统现在有这些核心对象：

- `Customer`
- `Conversation`
- `Message`
- `Ticket`
- `Subscription`
- `KnowledgeBase`
- `Document`
- `Chunk`
- `AgentTask`
- `Tool`
- `User`
- `Role`
- `Permission`

但这里有一个很重要的原则：

> **不是看到一个名词就建一张表。**
>
> 我们要从业务行为推导对象。

---

## 一、先建立整个业务世界

先看全局：

```
                         企业 AI 客服平台
                                │
        ┌───────────────────────┼───────────────────────┐
        ↓                       ↓                       ↓
     用户体系                客服业务                 AI体系
        │                       │                       │
   User/Role              Customer                 AgentTask
   Permission             Conversation                 │
                           Message                     Tool
                           Ticket                       │
                           Subscription                 │
                                                       AI
                                                        │
                              ┌─────────────────────────┘
                              ↓
                           知识库
                              │
                        KnowledgeBase
                              │
                          Document
                              │
                            Chunk
```

可以先把它理解成三个世界：

- **用户世界**
- **业务世界**
- **AI 世界**

---

## 二、User：谁在使用系统？

首先是最基础的：

```
User
```

它代表：

> 系统里的一个账号。

例如：

```
张三
账号：zhangsan
密码：******
角色：客服
```

**User 负责：**

- 身份
- 登录
- 账号状态
- 基本信息

**不负责：**

- 订单
- AI 回答
- 知识库
- 客服业务

所以：

```
User
 │
 └── 身份
```

---

## 三、Role：这个人是谁？

`User` 解决："你是谁？"

`Role` 解决："你是什么角色？"

例如：

```
User
 ↓
Role
 ↓
Customer
Agent
Admin
```

更准确一点：

```
User
 │
 └── Role
      ├── Customer
      ├── Agent
      └── Admin
```

> **但是这里不要把 Customer 直接理解成 Role。**
>
> 这是一个很容易踩坑的地方。

---

## 四、Customer：真正的企业客户

我们的 SaaS 公司有很多客户。

例如：

```
User
 ↓
张三
 ↓
Customer
 ↓
ABC科技
```

这里：

- **User = 系统账号**
- **Customer = 业务上的客户**

**为什么要拆？**

因为未来可能：

```
一个 Customer
 ↓
多个 User
```

例如 ABC 科技是一家公司：

```
ABC科技
 │
 ├── 张三
 ├── 李四
 └── 王五
```

他们都是同一个企业客户。

所以我们以后实际上可以继续演进成：

```
Tenant / Organization
        ↓
     Customer
        ↓
       User
```

> 不过第一版先不要把多租户搞复杂。

---

## 五、Conversation：一次对话

客户打开 AI 客服：

```
Customer
    ↓
Conversation
```

例如：

```
Conversation #10001

客户：我的套餐什么时候到期？
AI：您的套餐将在 12 月 31 日到期。
客户：那怎么续费？
AI：您可以进入……
```

所以：

```
Customer
   │
   └── Conversation
             │
             ├── Message
             ├── Message
             └── Message
```

一个客户：

```
Customer
 ↓
Conversation 1
Conversation 2
Conversation 3
```

**关系：**

```
Customer 1 : N Conversation
```

---

## 六、Message：真正的一句话

**Conversation 是：** 一个聊天容器。

**Message 是：** 聊天里面的一条消息。

例如：

```
Conversation #10001
│
├── Message #1
│     user
│     "我的套餐什么时候到期？"
│
├── Message #2
│     assistant
│     "您的套餐将在 12 月 31 日到期。"
│
└── Message #3
      user
      "怎么续费？"
```

所以：

```
Conversation
      │
      └── Message
```

**关系：**

```
Conversation 1 : N Message
```

---

## 七、Message 不只是 text

真实 AI 系统里，我们不能只设计 `message.content`。

还需要知道：

- 谁发送的？
- 什么类型？
- 什么时候发送？
- AI 还是人工？

因此 Message 至少需要：

```
Message
├── id
├── conversation_id
├── sender_type
├── sender_id
├── content
├── message_type
├── created_at
└── metadata
```

例如 `sender_type`：

```
USER
AI
AGENT
SYSTEM
```

这样以后我们就能区分：

- 客户说的
- AI 说的
- 人工客服说的
- 系统产生的

---

## 八、Ticket：工单

**什么时候产生 Ticket？**

```
AI无法解决
        ↓
需要人工处理
        ↓
创建工单
```

例如：

```
Conversation
 ↓
客户投诉退款
 ↓
AI判断需要人工
 ↓
Ticket
 ↓
客服处理
```

所以：

```
Conversation
      │
      └──── Ticket
```

一个会话：

```
Conversation
 ↓
Ticket
```

第一版我们可以设计成：

```
Conversation 1 : 0..1 Ticket
```

也就是说：**一个会话可以没有工单，也可以产生一个工单。**

---

## 九、Ticket 和 Conversation 为什么不能合并？

这是非常重要的领域建模问题。

你可能会想：

> "既然工单就是聊天，那直接在 Conversation 里面加 status 不就行了？"

**不建议。**

因为两者生命周期不同。

**Conversation 关注：**

- 聊天
- 消息
- 上下文
- AI
- 人工接管

**Ticket 关注：**

- 问题处理
- 负责人
- 优先级
- 状态
- 处理时间
- 解决时间

所以：

```
Conversation = 沟通
Ticket = 问题处理流程
```

**这是两个不同的业务概念。**

---

## 十、Subscription：客户买了什么套餐？

我们的 SaaS 企业需要实时业务数据。

例如客户问：

> "我的套餐什么时候到期？"

这时候不能让 RAG 猜。

因为这是**实时业务数据**。

所以我们建立：

```
Subscription
```

例如：

```
Subscription
├── customer_id
├── plan
├── status
├── start_at
├── expires_at
└── ...
```

关系：

```
Customer
   │
   └── Subscription
```

一个客户可能有多个订阅历史：

```
Customer
 │
 ├── Subscription #1
 │
 ├── Subscription #2
 │
 └── Subscription #3
```

所以：

```
Customer 1 : N Subscription
```

---

## 十一、为什么 Subscription 是 AI Agent 的关键？

客户问："我的套餐什么时候到期？"

AI 的处理链路：

```
Agent
 ↓
判断需要实时数据
 ↓
调用 Tool
 ↓
get_subscription()
 ↓
SubscriptionRepository
 ↓
MySQL
 ↓
Subscription
 ↓
返回 Agent
 ↓
LLM
 ↓
回答
```

所以：

```
Agent
 ↓
Tool
 ↓
Service
 ↓
Repository
 ↓
Subscription
```

这就是我们后面要实现的完整链路。

---

## 十二、KnowledgeBase：企业知识库

现在进入 AI 世界。

企业可能有：

- 产品使用手册
- 售后政策
- 退款规则
- FAQ
- API 文档
- 内部制度

我们需要一个：

```
KnowledgeBase
```

例如：

```
KnowledgeBase
└── 产品帮助中心
```

---

## 十三、Document：一份文档

一个知识库：

```
KnowledgeBase
 │
 ├── 产品手册.pdf
 ├── 退款政策.pdf
 ├── FAQ.md
 └── 用户指南.docx
```

所以：

```
KnowledgeBase 1 : N Document
```

`Document` 表示：

> 企业上传的一份原始知识文档。

例如：

```
Document
├── id
├── knowledge_base_id
├── name
├── file_url
├── file_type
├── status
├── created_at
└── ...
```

---

## 十四、Chunk：为什么还需要 Chunk？

这是 RAG 最重要的基础概念之一。

假设：`退款政策.pdf` 有 100 页。

我们不能直接把 100 页全部扔给 Embedding。

所以：

```
Document
 ↓
解析
 ↓
Chunk
```

例如：

```
Document
│
├── Chunk 1
├── Chunk 2
├── Chunk 3
├── ...
└── Chunk 500
```

一个 Document：

```
1 : N
```

多个 Chunk。

---

## 十五、Chunk 是 RAG 的核心数据

例如：

```
Chunk #1001

"用户申请退款后，
平台将在 3-5 个工作日内完成处理……"
```

然后：

```
Chunk
 ↓
Embedding
 ↓
Vector
 ↓
Milvus
```

> **所以要注意：**
>
> - Chunk 是业务数据 / 知识切片
> - Vector 是它经过模型计算得到的检索表示
>
> **不要把 `Chunk = Vector` 混为一谈。**

---

## 十六、AgentTask：Agent 做过什么任务？

进入 Agent。

例如用户说：

> "帮我查订单，如果过期就创建工单。"

Agent：

```
AgentTask
 ↓
Task 1：查询订阅
 ↓
Task 2：判断状态
 ↓
Task 3：创建工单
```

所以 AgentTask 可以记录：

```
AgentTask
├── id
├── conversation_id
├── task_type
├── status
├── input
├── output
├── started_at
├── finished_at
└── error
```

**它的价值在于：** 让 Agent 的执行过程可追踪。

未来做：

- Agent Evaluation
- Tracing
- 失败分析
- 任务重试

都会用到。

---

## 十七、Tool：Agent 可以使用的工具

**Tool 和 AgentTask 不一样。**

`Tool` 表示：

> Agent 可以使用什么**能力**。

例如：

```
get_customer
get_subscription
get_ticket
create_ticket
handoff_to_human
search_knowledge
```

`AgentTask` 表示：

> Agent 某一次**具体执行了什么任务**。

所以：

```
Tool = 能力
AgentTask = 一次执行记录
```

**这个区别以后非常重要。**

---

## 十八、现在把所有对象串起来

终于可以看完整关系：

```
                         User
                          │
                          ↓
                         Role
                          │
                          │
                       Customer
                    ┌─────┼──────┐
                    ↓     ↓      ↓
             Subscription  │   Conversation
                           │       │
                           │       ↓
                           │     Message
                           │       │
                           │       ↓
                           │     Ticket
                           │
                           │
                           ↓
                        AI Agent
                           │
                    ┌──────┼──────┐
                    ↓      ↓      ↓
                  Tool   RAG    AgentTask
                           │
                           ↓
                     KnowledgeBase
                           │
                           ↓
                       Document
                           │
                           ↓
                         Chunk
```

不过这里需要稍微修正一下：

> **AI Agent 并不是 Customer 的子对象。**

更准确的业务关系应该是：

```
Customer
   │
   └── Conversation
            │
            ├── Message
            │
            ├── AgentTask
            │
            └── Ticket

Customer
   │
   └── Subscription

KnowledgeBase
   │
   └── Document
          │
          └── Chunk

Agent
   │
   └── Tool
```

---

## 十九、形成第一版领域模型

现在可以正式整理：

| 领域 | 对象 | 核心职责 |
|------|------|----------|
| 用户 | User | 系统账号 |
| 权限 | Role | 角色 |
| 权限 | Permission | 具体权限 |
| 客户 | Customer | 企业客户 |
| 业务 | Subscription | 客户订阅 |
| 会话 | Conversation | 一次客服会话 |
| 会话 | Message | 一条消息 |
| 客服 | Ticket | 问题处理流程 |
| AI | AgentTask | Agent 执行任务 |
| AI | Tool | Agent 可调用能力 |
| 知识库 | KnowledgeBase | 知识集合 |
| 知识库 | Document | 原始文档 |
| 知识库 | Chunk | 文档切片 |

---

## 二十、最重要：领域模型 ≠ 数据库表

你现在一定要记住：

```
领域模型
   ↓
思考业务是什么
```

而：

```
SQLAlchemy Model
   ↓
思考数据库怎么存
```

两者有关，但不是一回事。

例如：

- 业务概念 `Customer`，以后可能对应 `customers` 表。

但：

> "客服是否接管会话"

不一定非要创建一个 `Handoff` 表。

它可能只是：

```
conversation.status
```

或者：

```
conversation.assigned_agent_id
```

**数据库设计是下一阶段才做的事情。**

---

## 二十一、我们现在发现了一个非常关键的问题

到这里，我们的业务模型已经出来了。

但是还有一个问题：

> "客户 → AI → RAG / Tool / 人工"到底具体怎么流转？

例如：

**场景 A：知识问题**

```
客户
 ↓
Conversation
 ↓
Message
 ↓
AI
 ↓
RAG
 ↓
KnowledgeBase
 ↓
Document
 ↓
Chunk
 ↓
LLM
 ↓
Message
```

**场景 B：业务问题**

```
客户
 ↓
Conversation
 ↓
Message
 ↓
Agent
 ↓
Tool
 ↓
Subscription
 ↓
LLM
 ↓
Message
```

**场景 C：人工接管**

```
客户
 ↓
Conversation
 ↓
AI
 ↓
判断无法解决
 ↓
Ticket
 ↓
Agent
 ↓
Message
 ↓
客户
```

> 这三个流程会决定我们后面的 Service 怎么拆、Domain 怎么拆、Repository 怎么拆。

---

## 二十二、所以第二阶段下一步

我建议我们继续按照真实项目设计，而不是现在就进入 SQL。

**下一步做：**

> 《第三阶段：核心业务流程设计》

我们把这 5 条核心链路完整画出来：

```
① 客户注册 → 登录 → 进入客服

② 客户 → AI → RAG → 回答

③ 客户 → AI → Agent → Tool → MySQL → 回答

④ AI 无法解决 → 转人工 → Ticket → 客服处理

⑤ 管理员上传 PDF → Chunk → Embedding → Milvus
```

然后我们再从这些流程反推：

```
业务流程
 ↓
领域模型
 ↓
数据库 ER 图
 ↓
Repository
 ↓
Service
 ↓
Router
```

> 到那一步，你之前一直没完全搞懂的 **Router / Service / Domain / Repository / Infrastructure**，就会第一次真正"落地"到这个项目里。
