# 《企业 AI 客服平台》第三阶段：核心业务流程设计 V1.0

> 前文：《企业 AI 客服平台》PRD V1.0 → 《企业 AI 客服平台》第二阶段：领域模型设计 V1.0

## 本阶段要解决的问题

> 很好。现在先不碰 SQL。

我们这一阶段真正要解决的问题是：

> **这个企业 AI 客服系统，到底是怎么"跑起来"的？**

第二阶段我们已经有了领域模型，现在第三阶段要把这些模型串成真实业务链路。

---

## 一、先确定整个系统的 5 条核心链路

我们把系统想象成一个真正上线的企业 AI 客服平台：

```
                    企业 AI 客服系统
                         │
        ┌────────────────┼────────────────┐
        │                │                │
      客户端           AI客服           管理后台
        │                │                │
        │                │                │
        ▼                ▼                ▼
     登录认证          RAG / Agent       知识库
                         │              管理
                         │
              ┌──────────┴──────────┐
              │                     │
             RAG                  Agent
              │                     │
              │              ┌──────┴──────┐
              │              │             │
              │            Tool          MySQL
              │
              ▼
             回答
              │
              ▼
          无法解决？
              │
             YES
              │
              ▼
           转人工
              │
              ▼
            Ticket
              │
              ▼
           客服处理
```

**5 条核心链路：**

1. 链路①：客户注册 → 登录 → 进入客服（用户身份链路）
2. 链路②：客户 → AI → RAG → 回答（AI 知识问答链路）
3. 链路③：客户 → AI → Agent → Tool → MySQL → 回答（AI 业务操作链路）
4. 链路④：AI 无法解决 → 转人工 → Ticket → 客服处理（人工客服链路）
5. 链路⑤：管理员上传 PDF → Chunk → Embedding → Milvus（知识库入库链路）

我们接下来逐条拆。

---

## 二、链路①：客户注册 → 登录 → 进入客服

这是整个系统的用户身份链路。

### 2.1 用户注册

假设客户访问：

```
POST /api/v1/auth/register
```

请求：

```json
{
    "username": "zhangsan",
    "password": "123456"
}
```

业务流程：

```
用户
 │
 │ 注册
 ▼
Router
 │
 ▼
AuthService
 │
 ├── 校验用户名
 │
 ├── 校验密码
 │
 ├── 密码 Hash
 │
 └── 创建用户
       │
       ▼
   UserRepository
       │
       ▼
      MySQL
```

> 注意这里第一次出现了我们第二阶段说的：Router / Service / Repository / Infrastructure。
> 但是现在先不要急着背概念，我们先看业务。

---

## 三、注册的时候到底发生了什么？

例如：

```
POST /register
```

进入 `AuthRouter`。

**Router 不应该自己写：**

- 查询数据库
- 创建用户
- 密码加密
- 判断用户名
- 生成 Token

**Router 最好只负责：**

> 接收 HTTP 请求，然后把业务交给 Service。

所以：

```
AuthRouter
    │
    │ register(request)
    ▼
AuthService
    │
    ├── 检查用户
    ├── 密码处理
    └── 创建用户
          │
          ▼
    UserRepository
          │
          ▼
       Database
```

---

## 四、登录

注册以后：

```
POST /api/v1/auth/login
```

请求：

```json
{
    "username": "zhangsan",
    "password": "123456"
}
```

流程：

```
客户端
  │
  │ username + password
  ▼
AuthRouter
  │
  ▼
AuthService
  │
  ├── 查询用户
  │       │
  │       ▼
  │   UserRepository
  │       │
  │       ▼
  │      MySQL
  │
  ├── 验证密码
  │
  └── 生成 JWT
          │
          ▼
       返回 Token
```

例如：

```json
{
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer"
}
```

之后：

```
客户端
   │
   │ Authorization: Bearer xxx
   ▼
客服 API
```

系统就知道：

```
你是谁？          → User
你属于哪个企业？   → Tenant
你有什么权限？     → Role / Permission
```

---

## 五、为什么 JWT 在这里出现？

因为后面的所有业务都需要知道：**当前是谁？**

例如：

```
客户 A
    ↓
发送问题
    ↓
创建 Conversation
```

系统必须知道：

```
conversation.user_id = A
```

所以：

```
JWT
 ↓
解析身份
 ↓
current_user
 ↓
Conversation
 ↓
Message
 ↓
Ticket
```

---

## 六、链路①完整图

```
                    用户
                     │
              注册 / 登录
                     │
                     ▼
                AuthRouter
                     │
                     ▼
                AuthService
                     │
              ┌──────┴──────┐
              │             │
           用户校验       密码校验
              │             │
              └──────┬──────┘
                     ▼
              UserRepository
                     │
                     ▼
                   MySQL
                     │
                     ▼
                  JWT Token
                     │
                     ▼
                  客服系统
```

---

## 七、链路②：客户 → AI → RAG → 回答

这是这个项目最核心的 AI 链路。

假设客户问：

> "你们公司的退款政策是什么？"

请求：

```
POST /api/v1/chat
{
    "message": "你们公司的退款政策是什么？"
}
```

---

## 八、第一步：进入 ChatRouter

```
客户
 │
 │ "退款政策是什么？"
 ▼
ChatRouter
```

Router 的职责：

> "有人发来了一个聊天请求，我把它交给 ChatService。"

所以：

```
ChatRouter
    ↓
ChatService
```

---

## 九、ChatService 做什么？

ChatService 是整个客服流程的业务编排者之一。

它可能做：

1. 获取当前用户
2. 获取 Conversation
3. 保存用户 Message
4. 调用 AI
5. 获取 AI Answer
6. 保存 AI Message
7. 返回结果

所以：

```
ChatService
    │
    ├── 获取 Conversation
    │
    ├── 保存 User Message
    │
    ├── AI Pipeline
    │
    └── 保存 Assistant Message
```

---

## 十、AI Pipeline

现在真正进入 AI 部分：

```
ChatService
     │
     ▼
 AI Orchestrator
     │
     ▼
 用户问题
```

例如："你们公司的退款政策是什么？"

系统判断：这是一个知识库问题。

于是：

```
Question
   │
   ▼
Embedding
   │
   ▼
Milvus
   │
   ▼
召回相关 Chunk
   │
   ▼
Rerank
   │
   ▼
Prompt
   │
   ▼
LLM
   │
   ▼
Answer
```

---

## 十一、RAG 到底在这个项目里做什么？

假设知识库里有：

```
Chunk 1：本公司商品支持 7 天无理由退款。
Chunk 2：退款申请提交后，将在 3 个工作日内审核。
Chunk 3：特殊定制商品不支持无理由退款。
```

用户："可以退款吗？"

**系统首先不是直接问 LLM**，而是：

```
用户问题
   │
   ▼
Embedding
   │
   ▼
Milvus
   │
   ├── Chunk 1
   ├── Chunk 2
   └── Chunk 3
```

然后把这些知识给 LLM：

```
System:
你是企业客服。

Context:
本公司商品支持7天无理由退款。

User:
可以退款吗？
```

LLM 回答：

> 可以。如果商品符合 7 天无理由退款条件，可以申请退款。

---

## 十二、所以 RAG 的本质

你可以把它理解成：

```
LLM    = 会说话的大脑
Milvus = 企业知识库的搜索系统
RAG    = 先查资料，再让 LLM 回答
```

所以：

```
用户问题
   ↓
搜索企业知识
   ↓
把知识交给 LLM
   ↓
生成答案
```

---

## 十三、链路②完整图

```
客户
 │
 │ "退款政策是什么？"
 ▼
ChatRouter
 │
 ▼
ChatService
 │
 ▼
AI Orchestrator
 │
 ▼
Intent / Query Analysis
 │
 ▼
Embedding
 │
 ▼
Milvus
 │
 ▼
Top-K Chunks
 │
 ▼
Rerank
 │
 ▼
Prompt Builder
 │
 ▼
LLM
 │
 ▼
AI Answer
 │
 ▼
ChatService
 │
 ├── 保存 Message
 │
 ▼
返回客户
```

---

## 十四、链路③：客户 → AI → Agent → Tool → MySQL → 回答

这个链路非常重要。

因为：

- **RAG 解决"知识问题"**
- **Tool 解决"业务数据问题"**

例如客户问：

> "我的订单 10086 现在到哪里了？"

这个问题不能只查 PDF，因为订单状态是实时变化的。

---

## 十五、RAG 为什么解决不了？

知识库可能只有：

- 公司订单配送规则
- 退款规则
- 售后规则
- 会员规则

但是：

```
订单 10086
```

是**动态数据**。真正的数据在 MySQL。

所以必须：

```
AI
 ↓
Agent
 ↓
Tool
 ↓
OrderRepository
 ↓
MySQL
```

---

## 十六、Agent 是怎么判断的？

用户："帮我查一下订单 10086 到哪里了？"

Agent 分析：

```
Intent: 查询订单物流
Slot: order_id = 10086
```

然后决定：需要调用工具。

例如：

```
get_order_status(order_id=10086)
```

---

## 十七、Tool 是什么？

Tool 可以简单理解为：

> 给 Agent 使用的"业务能力接口"。

例如：

```
Tool
├── get_order()
├── get_order_status()
├── create_refund()
├── cancel_order()
├── query_user()
└── create_ticket()
```

例如 `get_order_status(order_id)`，背后真正执行：

```
Tool
 ↓
OrderService
 ↓
OrderRepository
 ↓
SQLAlchemy
 ↓
MySQL
```

---

## 十八、这里非常关键

**不要设计成：**

```
Agent
 ↓
直接操作 MySQL
```

这是不好的企业级设计。

**应该：**

```
Agent
 ↓
Tool
 ↓
Service
 ↓
Repository
 ↓
Database
```

**为什么？**

因为 Agent 不应该知道：

- SQL 怎么写
- 数据库在哪里
- 表叫什么
- SQLAlchemy 怎么使用

Agent 只需要知道：

> 我有一个能力：查询订单

---

## 十九、完整链路

用户："订单10086到哪里了？"

```
↓

ChatRouter

↓

ChatService

↓

AI Orchestrator

↓

Agent

↓

判断：需要查询订单

↓

Tool
get_order_status()

↓

OrderService

↓

OrderRepository

↓

SQLAlchemy

↓

MySQL

↓

返回：
{
    "order_id": "10086",
    "status": "配送中",
    "estimated_delivery": "2026-09-10"
}

↓

Agent：
你的订单 10086 目前正在配送中，
预计 9 月 10 日送达。

↓

客户。
```

---

## 二十、链路③完整图

```
                    客户
                     │
                     ▼
               ChatRouter
                     │
                     ▼
                ChatService
                     │
                     ▼
               AI Orchestrator
                     │
                     ▼
                   Agent
                     │
              判断需要 Tool
                     │
                     ▼
              get_order_status
                     │
                     ▼
               OrderService
                     │
                     ▼
             OrderRepository
                     │
                     ▼
                 SQLAlchemy
                     │
                     ▼
                   MySQL
                     │
                     ▼
                 Order Data
                     │
                     ▼
                   Agent
                     │
                     ▼
                Natural Language
                     │
                     ▼
                    客户
```

---

## 二十一、链路④：AI 无法解决 → 转人工 → Ticket → 客服处理

这是一个真正企业客服系统必须有的链路。

例如：

> 客户："我的商品已经损坏，我要求赔偿 5000 元。"

AI 判断：

- 无法自动处理
- 或高风险问题

于是：

```
AI
 ↓
TransferToHuman
```

---

## 二十二、为什么需要 Ticket？

因为：

**聊天 ≠ 工单**

- `Conversation` 是：客户和客服之间的对话记录。
- `Ticket` 是：一个需要被处理的业务任务。

例如：

```
Ticket #10001

标题：商品损坏赔偿
客户：张三
状态：OPEN
优先级：HIGH
负责人：客服001
```

---

## 二十三、转人工流程

```
客户
 │
 ▼
AI
 │
 ├── 能解决？
 │      │
 │     YES
 │      ▼
 │    AI回答
 │
 └── NO
       │
       ▼
    创建 Ticket
       │
       ▼
   TicketService
       │
       ▼
 TicketRepository
       │
       ▼
     MySQL
       │
       ▼
   分配客服
       │
       ▼
    Human Agent
       │
       ▼
    客服处理
       │
       ▼
    Ticket CLOSED
```

---

## 二十四、这里出现一个非常重要的业务关系

```
Conversation
     │
     │ 可能产生
     ▼
   Ticket
```

也就是说：

```
Conversation 1
 ├── Message
 ├── Message
 ├── Message
 │
 └── Ticket
       │
       ├── 状态
       ├── 优先级
       ├── 负责人
       └── 处理记录
```

---

## 二十五、链路④完整图

```
客户
 │
 ▼
Conversation
 │
 ▼
AI
 │
 ▼
判断是否能够解决
 │
 ├───────────────┐
 │               │
 YES             NO
 │               │
 ▼               ▼
AI回答          创建Ticket
                 │
                 ▼
             TicketService
                 │
                 ▼
            TicketRepository
                 │
                 ▼
               MySQL
                 │
                 ▼
             分配客服
                 │
                 ▼
              人工处理
                 │
                 ▼
            Ticket Closed
```

---

## 二十六、链路⑤：管理员上传 PDF → Chunk → Embedding → Milvus

现在来到知识库。

管理员进入**管理后台**，上传：

```
退款政策.pdf
```

---

## 二十七、上传文件之后发生什么？

```
管理员
 │
 │ 上传 PDF
 ▼
KnowledgeRouter
 │
 ▼
KnowledgeService
 │
 ▼
Document
 │
 ▼
PDF Parser
 │
 ▼
Text
 │
 ▼
Chunk
 │
 ▼
Embedding
 │
 ▼
Milvus
```

---

## 二十八、为什么需要 Chunk？

假设 PDF 有 100 页。

不能直接：

```
100页PDF
 ↓
Embedding
```

通常需要：

```
PDF
 ↓
解析文本
 ↓
切分
 ↓
Chunk
```

例如：

```
Document
│
├── Chunk 001
├── Chunk 002
├── Chunk 003
├── Chunk 004
├── ...
└── Chunk 500
```

---

## 二十九、Embedding 做什么？

例如：

> "商品支持七天无理由退款"

经过 Embedding：

```
[0.021, -0.182, 0.734, ...]
```

变成一个向量。

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

---

## 三十、为什么放 Milvus？

因为用户以后问：

> "我买东西以后能退吗？"

这句话和：

> "商品支持七天无理由退款"

文字不完全一样，但是**语义相近**。

Milvus 可以做：

```
Query Vector
      ↓
   Similarity
      ↓
Chunk 001
Chunk 023
Chunk 087
```

然后交给 LLM。

---

## 三十一、链路⑤完整图

```
管理员
 │
 │ 上传 PDF
 ▼
KnowledgeRouter
 │
 ▼
KnowledgeService
 │
 ▼
Document
 │
 ▼
PDF Parser
 │
 ▼
Text
 │
 ▼
Text Chunker
 │
 ▼
Chunks
 │
 ▼
Embedding Model
 │
 ▼
Vectors
 │
 ▼
Milvus
 │
 ▼
Knowledge Base
```

---

## 三十二、现在把 5 条链路放在一起

这才是整个项目的核心业务架构。

```
                         企业 AI 客服
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
        客户端               AI系统             管理后台
          │                   │                   │
          │                   │                   │
          ▼                   ▼                   ▼
      AuthRouter          AI Orchestrator    KnowledgeRouter
          │                   │                   │
          ▼                   │                   ▼
      AuthService             │             KnowledgeService
          │                   │                   │
          ▼                   │             PDF → Chunk
      UserRepository          │                   │
          │                   │              Embedding
          ▼                   │                   ▼
        MySQL                 │                 Milvus
                              │
                    ┌─────────┴─────────┐
                    │                   │
                   RAG                Agent
                    │                   │
                    ▼                   ▼
                  Milvus              Tool
                    │                   │
                    │                   ▼
                    │                Service
                    │                   │
                    │                   ▼
                    │               Repository
                    │                   │
                    │                   ▼
                    │                 MySQL
                    │
                    ▼
                   LLM
                    │
                    ▼
                  Answer
                    │
                    ▼
                无法解决？
                    │
                   YES
                    │
                    ▼
                  Ticket
                    │
                    ▼
                Human Agent
```

---

## 三十三、现在开始反推六层架构

这一步才是第三阶段最重要的地方。

我们现在不再抽象地讲"Router 是什么？"，而是直接从真实业务里面看。

### ① Router

Router 负责：**HTTP 世界 → 业务世界**

例如：

```
POST /chat
```

进入 `ChatRouter`。

它处理：

- Request
- 参数
- 认证
- Response
- HTTP Status Code

但它不应该负责核心业务逻辑。

---

## 三十四、② Service

Service 负责：**完成一个业务动作**。

例如：

```
ChatService
AuthService
TicketService
KnowledgeService
OrderService
```

比如 `ChatService.send_message()` 里面可能：

```
保存 Message
    ↓
调用 AI
    ↓
保存 Answer
```

所以：

```
Router
 ↓
Service
```

你可以暂时把 Service 理解成：**业务流程负责人**。

---

## 三十五、③ Domain

Domain 是：**业务规则本身**。

例如 Ticket 状态机：

```
OPEN
 ↓
PROCESSING
 ↓
RESOLVED
 ↓
CLOSED
```

这里有规则：**CLOSED 不能重新变成 OPEN**。这个就是业务规则。

又例如：订单已发货，不能直接取消订单，也是业务规则。

所以：

```
Domain = 这个企业的"业务规则大脑"
```

---

## 三十六、④ Repository

Repository 负责：**业务对象怎么存、怎么查**。

例如：

```
UserRepository
OrderRepository
TicketRepository
ConversationRepository
MessageRepository
```

Service 不应该关心：

```
SELECT * FROM orders WHERE id = ...
```

Service 只需要：

```python
order = order_repository.get_by_id(order_id)
```

Repository 去处理：

```
SQLAlchemy
 ↓
MySQL
```

---

## 三十七、⑤ Infrastructure

Infrastructure 是：**真正和外部技术世界打交道的东西**。

例如：

```
MySQL
Redis
Milvus
LLM API
Object Storage
MQ
Email
```

所以：

```
Repository
     ↓
Infrastructure
     ↓
SQLAlchemy
     ↓
MySQL
```

**AI：**

```
Agent
 ↓
Tool
 ↓
Service
 ↓
Repository
 ↓
Infrastructure
```

**RAG：**

```
RAGService
 ↓
MilvusRepository
 ↓
Milvus
```

---

## 三十八、⑥ Common

Common 放：**整个项目都可能使用的通用能力**。

例如：

```
exceptions
logger
response
security
constants
utils
middleware
```

比如：

- JWT
- 统一异常
- 日志
- 分页
- 时间工具

---

## 三十九、现在终于可以看到六层之间的关系

不是六个孤零零的文件夹：

```
Router
Service
Domain
Repository
Infrastructure
Common
```

而是：

```
                   HTTP
                    │
                    ▼
                 Router
                    │
                    ▼
                 Service
                    │
             ┌──────┴──────┐
             │             │
             ▼             ▼
           Domain      Repository
                           │
                           ▼
                    Infrastructure
                           │
                    ┌──────┼──────┐
                    ▼      ▼      ▼
                  MySQL  Redis   Milvus
```

而 `Common` 是横向支撑：

```
Router
Service
Domain
Repository
Infrastructure
   ↑
 Common
```

---

## 四十、但是 AI 项目会比普通后端多一层什么？

这里就开始进入我们这个项目的特色了：

**传统企业后端：**

```
Router
 ↓
Service
 ↓
Domain
 ↓
Repository
 ↓
MySQL
```

**AI 客服：**

```
Router
 ↓
ChatService
 ↓
AI Orchestrator
 ↓
 ┌──────────────┐
 │              │
 ▼              ▼
 RAG           Agent
 │              │
 ▼              ▼
Milvus         Tool
                │
                ▼
             Service
                │
                ▼
           Repository
                │
                ▼
              MySQL
```

> 所以你以后做 AI Agent 后端，不是抛弃传统后端。
> 而是在**传统企业后端之上，增加 AI 编排能力**。

---

## 四十一、第三阶段我们现在得到的最终结果

目前我们已经把 5 条链路都串起来了：

**① 身份系统：**

```
Register
Login
JWT
User
```

**② AI 知识问答：**

```
Question
 ↓
RAG
 ↓
Milvus
 ↓
LLM
 ↓
Answer
```

**③ AI 业务操作：**

```
Question
 ↓
Agent
 ↓
Tool
 ↓
Service
 ↓
Repository
 ↓
MySQL
 ↓
Answer
```

**④ 人工客服：**

```
AI
 ↓
无法解决
 ↓
Ticket
 ↓
客服
 ↓
处理完成
```

**⑤ 知识库：**

```
PDF
 ↓
Parser
 ↓
Chunk
 ↓
Embedding
 ↓
Milvus
```

---

## 四十二、下一步就到了真正的"数据库设计"

现在我们终于有资格开始设计数据库了。

因为数据库不是凭空设计（先建 user 表、先建 order 表、先建 ticket 表），而应该：

```
业务流程
     ↓
发现业务对象
     ↓
发现对象之间的关系
     ↓
领域模型
     ↓
数据库实体
     ↓
ER 图
     ↓
表结构
```

所以我们的下一阶段应该正式进入：

> **《第四阶段：数据库 ER 模型设计》**

我们会从刚才的 5 条链路，一张表一张表地反推：

```
User
Tenant
Role
Permission

Conversation
Message

Ticket
TicketMessage
TicketAssignment

Document
DocumentChunk
KnowledgeBase

Order
...
```

然后画出：

```
User
 │
 ├──────── Conversation
 │               │
 │               └──── Message
 │
 └──────── Ticket
                 │
                 └──── Assignment

KnowledgeBase
 │
 └──── Document
          │
          └──── Chunk
                    │
                    └──── Vector → Milvus
```

最后再把它真正落到：

```
MySQL
 ↓
SQLAlchemy Model
 ↓
Repository
```

> 这时候你之前一直觉得抽象的 Router → Service → Domain → Repository → Infrastructure，就会从"概念"变成这个真实 AI 客服项目里的实际代码结构。
