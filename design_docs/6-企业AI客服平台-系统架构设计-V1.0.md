# 《企业 AI 客服平台》第六阶段：系统架构设计 V1.0

> 前文：PRD V1.0 → 领域模型设计 → 核心业务流程设计 → 数据库 ER 模型设计 → 完整开发路线图（总施工图）

## 本阶段要解决的问题

目标不是马上写代码，而是回答一个问题：

> **这么多业务、这么多技术，代码到底应该放在哪里？一次用户请求到底经过哪些模块？**

我们按照真实企业 AI 客服项目来设计。

---

## 一、先确定整体架构

我们这个项目先采用：**模块化单体架构（Modular Monolith）**，而不是一开始就微服务。

整体：

```
                    ┌─────────────────────┐
                    │       Client        │
                    │ Web / App / 微信等  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       Nginx         │
                    │ HTTPS / 反向代理    │
                    └──────────┬──────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                  │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Auth     │  │ Chat     │  │ Knowledge│              │
│  │ Module   │  │ Module   │  │ Module   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Ticket   │  │ User     │  │ Admin    │              │
│  │ Module   │  │ Module   │  │ Module   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                         │
│              ┌──────────────────────────┐               │
│              │     AI Application       │               │
│              │                          │               │
│              │ Router → Agent → RAG     │               │
│              │           ↓              │               │
│              │        LLM / API         │               │
│              └──────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
              │              │              │
              ▼              ▼              ▼
          PostgreSQL       Redis          Milvus
              │
              ▼
          Object Storage

                 ┌─────────────────┐
                 │ Message Queue   │
                 │ Celery / MQ     │
                 └────────┬────────┘
                          │
                          ▼
                    Async Workers
```

---

## 二、为什么选择模块化单体？

我们之前已经讨论过演进路径：

```
单体
 ↓
模块化单体
 ↓
微服务
```

这个项目现在选择**模块化单体**，原因非常现实。

如果一开始就上微服务：

```
用户服务
 ↓
会话服务
 ↓
AI服务
 ↓
RAG服务
 ↓
知识库服务
 ↓
工单服务
 ↓
网关
 ↓
注册中心
 ↓
MQ
```

对于学习和第一版开发来说，会产生**大量分布式复杂度**。

我们现在希望先把：

- 业务边界
- 代码结构
- AI 链路
- 数据链路
- 异步链路

全部设计清楚。

以后真的需要拆微服务，可以：

```
Chat Module      → Chat Service
Knowledge Module → Knowledge Service
Ticket Module    → Ticket Service
```

所以：**模块化单体是为未来微服务拆分留下边界。**

---

## 三、代码总体目录

最终项目采用：

```
app/
│
├── main.py
│
├── config/
│
├── common/
│
├── infrastructure/
│
├── modules/
│
├── ai/
│
└── tasks/
```

进一步展开：

```
app/
│
├── main.py
│
├── config/
│   ├── settings.py
│   └── database.py
│
├── common/
│   ├── exceptions/
│   ├── response/
│   ├── middleware/
│   ├── utils/
│   └── constants/
│
├── infrastructure/
│   ├── database/
│   ├── redis/
│   ├── milvus/
│   ├── storage/
│   ├── mq/
│   └── llm/
│
├── modules/
│   │
│   ├── auth/
│   ├── user/
│   ├── chat/
│   ├── knowledge/
│   ├── ticket/
│   └── admin/
│
├── ai/
│   ├── router/
│   ├── agent/
│   ├── rag/
│   ├── memory/
│   ├── prompt/
│   └── models/
│
└── tasks/
    ├── document_tasks.py
    ├── embedding_tasks.py
    ├── cleanup_tasks.py
    └── notification_tasks.py
```

> 这里有一个非常重要的思想：**业务模块和 AI 能力分开。**

---

## 四、为什么 AI 不直接塞进 ChatService？

这是这个项目架构里非常重要的一点。

**错误方式：**

```
ChatService
    │
    ├── 调 LLM
    ├── 查 Milvus
    ├── 判断意图
    ├── Agent
    ├── Prompt
    ├── 保存消息
    └── 调业务 API
```

最后 `ChatService.py` 变成 2000 行，非常难维护。

**所以我们拆开：**

```
Chat
 │
 └── AI Application
        │
        ├── AI Router
        ├── Agent
        ├── RAG
        ├── Memory
        ├── Prompt
        └── LLM
```

---

## 五、模块内部继续采用六层架构

这和你之前问的 `router / service / domain / repository / infrastructure / common` 结合起来。

例如 Chat：

```
modules/chat/

├── router.py
├── schemas.py
├── service.py
├── domain/
│   ├── conversation.py
│   └── message.py
│
└── repository/
    ├── conversation_repository.py
    └── message_repository.py
```

所以整个架构实际上是：

```
模块化
+
六层架构
```

即：

```
                Application
                     │
        ┌────────────┼────────────┐
        │            │            │
       Auth         Chat       Knowledge
        │            │            │
        ▼            ▼            ▼
     Router       Router       Router
        │            │            │
     Service      Service      Service
        │            │            │
     Domain       Domain       Domain
        │            │            │
   Repository   Repository   Repository
        │            │            │
        └────────────┼────────────┘
                     │
              Infrastructure
```

---

## 六、六层到底分别干什么？

这一阶段把它彻底固定下来。

### 1. Router

负责：HTTP。

例如 `POST /api/v1/chat`，Router 做：

```
接收请求
 ↓
参数校验
 ↓
调用 Service
 ↓
返回 Response
```

Router：**不写业务逻辑。**

---

## 七、Service

Service 是**业务用例层**。

例如 `chat_service.chat()` 负责组织：

```
创建会话
 ↓
保存用户消息
 ↓
调用 AI
 ↓
保存 AI 消息
 ↓
返回结果
```

它是**业务流程的组织者**。

---

## 八、Domain

Domain 是**业务规则**。

例如：

- 什么情况下可以创建工单？
- 什么情况下转人工？
- 什么情况下关闭会话？
- 什么情况下允许重新分配？

例如：

```python
if conversation.can_create_ticket():
    ...
```

Domain 不关心：

```
FastAPI
MySQL
Redis
Milvus
```

它只关心：**业务规则本身。**

---

## 九、Repository

Repository 负责访问数据库。

例如：

```python
conversation_repository.get_by_id()
```

里面使用：

```
SQLAlchemy
 ↓
PostgreSQL
```

Service 不应该到处写 `session.query(...)`，而应该：

```
Service
 ↓
Repository
 ↓
SQLAlchemy
 ↓
PostgreSQL
```

---

## 十、Infrastructure

Infrastructure 是**外部技术系统的实现**。

例如：

```
PostgreSQL
Redis
Milvus
LLM
MQ
S3
```

所以：

```
infrastructure/
│
├── database/
├── redis/
├── milvus/
├── llm/
├── mq/
└── storage/
```

---

## 十一、AI 架构

现在进入这个项目最核心的部分。

我们设计：

```
用户问题
   ↓
AI Router
   ↓
Intent
   ↓
Agent
   ↓
决定下一步
   │
   ├──────────────┐
   ↓              ↓
 RAG            Business API
   ↓              ↓
Milvus          业务数据库
   │              │
   └──────┬───────┘
          ↓
         LLM
          ↓
       Answer
```

但这里需要进一步优化。

---

## 十二、一次 AI 请求到底怎么走？

例如用户问："你们家的退款多久到账？"

请求：

```
POST /api/v1/chat
```

进入：

```
ChatRouter
 ↓
ChatService
 ↓
保存用户消息
 ↓
AIApplication
 ↓
AI Router
 ↓
判断：这是一个什么问题？
得到：Intent = refund_arrival_time
 ↓
判断是否需要知识？需要
 ↓
进入 RAG：
    Query Rewrite
       ↓
    Hybrid Retrieval
       ↓
    Milvus + BM25/ES
       ↓
    Rerank
 ↓
得到 Top K Documents
 ↓
交给 Agent / LLM
 ↓
生成：退款一般会在 3～5 个工作日到账……
 ↓
保存 AI Message
 ↓
通过 SSE 返回前端
```

---

## 十三、动态问题怎么办？

例如："帮我查一下订单 123456 现在到哪里了？"

这时候不能只靠 RAG，因为**订单状态是实时数据**。

所以：

```
用户问题
 ↓
AI Router
 ↓
Intent = query_order
 ↓
Slot: order_id = 123456
 ↓
Agent
 ↓
Business API
 ↓
Order Service
 ↓
Database
 ↓
返回订单状态
 ↓
LLM 组织语言
 ↓
返回用户
```

这就是我们之前讨论过的：

> **RAG 负责知识，Business API 负责实时业务数据。**

---

## 十四、Agent 到底干什么？

Agent 不是"一个神秘的大模型"，而是：

> **根据当前任务决定下一步调用什么能力。**

例如：

```
Agent
 │
 ├── search_knowledge()
 ├── query_order()
 ├── create_ticket()
 ├── transfer_human()
 └── answer()
```

例如用户说"我的订单为什么还没到？"：

```
Agent 判断：需要查询订单
调用 query_order()
得到：运输中，预计明天到达
然后 LLM 组织自然语言
```

---

## 十五、RAG 在架构中的位置

RAG 不应该直接写进 Router。

**错误方式：**

```
Router
 ↓
Milvus
 ↓
LLM
```

**应该：**

```
Router
 ↓
ChatService
 ↓
AIApplication
 ↓
RAG
 ↓
Retriever
 ↓
Milvus / ES
```

RAG 内部：

```
ai/rag/

├── retriever.py
├── query_rewrite.py
├── hybrid_search.py
├── reranker.py
└── context_builder.py
```

---

## 十六、Milvus 放在哪里？

Milvus 是基础设施，所以：

```
ai/rag
    ↓
infrastructure/milvus
```

关系：

```
RAG
 ↓
MilvusRepository
 ↓
Milvus SDK
 ↓
Milvus
```

这样以后如果从 Milvus 换成 pgvector，**不会把整个 RAG 重写**。

---

## 十七、Redis 放在哪里？

Redis 也是 Infrastructure：

```
infrastructure/redis/
```

上层可以使用它实现：

```
Session
Cache
Rate Limit
Distributed Lock
Conversation Memory
```

例如：

```
ChatService
    ↓
ConversationMemory
    ↓
Redis
```

而不是到处直接操作：

```
ChatService
    ↓
redis.set(...)
```

---

## 十八、异步任务怎么走？

这是企业系统非常重要的一条链路。

例如用户上传 PDF，**不能**：

```
HTTP Request
 ↓
解析PDF
 ↓
切块
 ↓
Embedding
 ↓
写Milvus
 ↓
Response
```

因为可能需要 30 秒 / 1 分钟 / 5 分钟。

所以：

```
上传文件
 ↓
保存 Document
 ↓
提交任务
 ↓
立即返回
```

然后：

```
Message Queue
       ↓
Worker
       ↓
PDF解析
       ↓
文本切块
       ↓
Embedding
       ↓
Milvus
       ↓
更新 document.status
```

---

## 十九、异步任务完整架构

```
                 FastAPI
                    │
                    ▼
             KnowledgeService
                    │
                    ▼
              Create Document
                    │
                    ▼
                 MQ / Redis
                    │
                    ▼
                  Worker
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Parser    Chunker   Embedder
          │         │         │
          └─────────┼─────────┘
                    ▼
                  Milvus
```

---

## 二十、哪些东西必须异步？

**必须 / 非常适合异步：**

```
PDF解析
Word解析
Excel解析
文档切块
Embedding
批量向量化
批量知识库导入
邮件发送
通知
日志归档
数据清理
```

**通常同步：**

```
登录
查询用户
查询会话
发送聊天消息
查询订单
创建工单
```

但是**聊天消息**内部可能同时涉及 `Streaming / LLM`，这属于：

```
异步 I/O / 流式响应
```

和**后台异步任务**不是同一个概念。这一点后面会专门讲。

---

## 二十一、完整请求链路

现在把整个系统串起来。

**普通 HTTP 请求：**

```
Client
 ↓
Nginx
 ↓
FastAPI
 ↓
Router
 ↓
Service
 ↓
Domain
 ↓
Repository
 ↓
SQLAlchemy
 ↓
PostgreSQL
```

---

## 二十二、AI 请求

```
Client
 ↓
Nginx
 ↓
FastAPI
 ↓
ChatRouter
 ↓
ChatService
 ↓
AIApplication
 ↓
AI Router
 ↓
Agent
 ├── RAG
 │    ├── Hybrid Search
 │    ├── Milvus
 │    └── Rerank
 │
 ├── Business API
 │
 └── Tool
       ↓
      LLM
       ↓
    Response
       ↓
    SSE Stream
       ↓
     Client
```

---

## 二十三、知识库上传链路

```
Client
 ↓
KnowledgeRouter
 ↓
KnowledgeService
 ↓
DocumentRepository
 ↓
PostgreSQL
 ↓
MQ
 ↓
Worker
 ↓
Document Parser
 ↓
Chunker
 ↓
Embedding
 ↓
Milvus
 ↓
Update Document Status
```

---

## 二十四、最终架构图

现在我们的整个企业 AI 客服系统可以抽象成：

```
                         Client
                           │
                           ▼
                        Nginx
                           │
                           ▼
                       FastAPI
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
        Auth             Chat          Knowledge
        Module           Module          Module
          │                │                │
          ▼                ▼                ▼
       Service          Service         Service
                           │
                           ▼
                     AI Application
                           │
                    ┌──────┼──────┐
                    │      │      │
                    ▼      ▼      ▼
                   RAG   Agent   Memory
                    │      │
                    │      ├──────► Business API
                    │      │
                    ▼      ▼
                 Milvus   LLM
                    │
                    │
          ┌─────────┴──────────┐
          │                    │
          ▼                    ▼
     PostgreSQL              Redis
          │
          │
          ▼
      Repository


Knowledge Upload
       │
       ▼
      MQ
       │
       ▼
    Workers
       │
       ├── Parser
       ├── Chunker
       ├── Embedding
       └── Index
```

---

## 二十五、这一阶段最终确定什么？

到这里，第六阶段我们正式确定：

| 维度 | 确定结果 |
|------|----------|
| 架构模式 | 模块化单体 |
| Web 框架 | FastAPI |
| 业务架构 | Router ↓ Service ↓ Domain ↓ Repository ↓ Infrastructure |
| AI 架构 | AI Router ↓ Agent ↓ RAG / Tool / Business API ↓ LLM |
| RAG | Hybrid Retrieval ↓ Milvus + Keyword Search ↓ Rerank ↓ Context |
| 缓存 | Redis |
| 数据库 | PostgreSQL |
| 异步 | MQ ↓ Worker |
| 实时输出 | SSE |

---

## 二十六、把整个项目的"层次"记住

你以后看企业 Python 项目，可以用这个视角：

```
┌─────────────────────────────┐
│        API 层               │
│ Router / Schema             │
├─────────────────────────────┤
│        Application 层       │
│ Service / UseCase           │
├─────────────────────────────┤
│        Domain 层            │
│ Business Rules              │
├─────────────────────────────┤
│        AI Application       │
│ Agent / RAG / Memory        │
├─────────────────────────────┤
│        Repository           │
│ Data Access                 │
├─────────────────────────────┤
│        Infrastructure       │
│ DB / Redis / MQ / Milvus    │
├─────────────────────────────┤
│        External             │
│ PostgreSQL / Redis / Milvus │
│ LLM / Object Storage        │
└─────────────────────────────┘
```

这时候你就会发现：

> Router、Service、Domain、Repository、Infrastructure 并不是五个孤立的文件夹，而是一条完整的请求链。

而 AI 也不是另外一套完全独立的系统：

**传统后端：**

```
Router
 ↓
Service
 ↓
Domain
 ↓
Repository
 ↓
DB
```

**变成 AI 客服后：**

```
Router
 ↓
Service
 ↓
AI Application
 ↓
Agent
 ├── RAG
 ├── Tool
 ├── Business API
 └── LLM
 ↓
Repository / Infrastructure
```

**这就是我们这个项目最核心的架构。**
