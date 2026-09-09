# 《企业 AI 客服平台》第八阶段：项目工程结构设计 V1.0（最终版）

> 前文：PRD → 领域模型 → 核心业务流程 → ER 模型 → 数据库表结构 → 系统架构 → API 接口设计

## 一、这一阶段到底解决什么问题？

前面我们已经知道：

```
系统做什么？      → PRD
系统有哪些业务对象？→ 领域模型
业务怎么运行？    → 核心业务流程
数据怎么存？      → 数据库 ER
接口怎么提供？    → API 设计
系统整体怎么组成？→ 系统架构
```

现在还差最后一个问题：

> **这些东西在 PyCharm 里面到底放在哪里？**

也就是：

- 一个真实 Python 项目到底应该怎么组织目录？
- 每个文件负责什么？
- 代码之间怎么依赖？
- 数据库放哪里？
- Redis 放哪里？
- RAG 放哪里？
- Agent 放哪里？
- 配置放哪里？
- 测试放哪里？

所以第八阶段就是：**从"架构图"落地到"代码目录"。**

---

## 二、我们最终采用什么工程结构？

我们的项目：`enterprise-ai-customer-service/`

采用：**模块化单体 Modular Monolith + 业务模块化 + 分层架构 + AI 能力层**

最终结构：

```
enterprise-ai-customer-service/
│
├── app/
│   │
│   ├── main.py
│   │
│   ├── api/
│   │   ├── router.py
│   │   └── dependencies.py
│   │
│   ├── modules/
│   │   │
│   │   ├── auth/
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── domain/
│   │   │   └── repository/
│   │   │
│   │   ├── user/
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── domain/
│   │   │   └── repository/
│   │   │
│   │   ├── chat/
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── domain/
│   │   │   └── repository/
│   │   │
│   │   ├── knowledge/
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── domain/
│   │   │   └── repository/
│   │   │
│   │   └── ticket/
│   │       ├── router.py
│   │       ├── schemas.py
│   │       ├── service.py
│   │       ├── domain/
│   │       └── repository/
│   │
│   ├── ai/
│   │   ├── router/
│   │   ├── agent/
│   │   ├── rag/
│   │   ├── memory/
│   │   ├── prompt/
│   │   ├── llm/
│   │   └── tools/
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── redis/
│   │   ├── milvus/
│   │   ├── mq/
│   │   ├── storage/
│   │   └── llm/
│   │
│   ├── models/
│   ├── schemas/
│   │
│   ├── tasks/
│   │   ├── document_tasks.py
│   │   ├── embedding_tasks.py
│   │   └── cleanup_tasks.py
│   │
│   ├── common/
│   │   ├── exceptions/
│   │   ├── response/
│   │   ├── middleware/
│   │   ├── logging/
│   │   └── utils/
│   │
│   └── config/
│       ├── settings.py
│       └── logging.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
├── alembic/
│
├── scripts/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
├── Dockerfile
└── README.md
```

接下来我们一个一个理解。

---

## 三、最外层：项目根目录

`enterprise-ai-customer-service/` 是**整个项目**。

里面主要分成：

```
app/
tests/
alembic/
scripts/
配置文件
依赖文件
Docker
README
```

可以理解成：

```
项目
│
├── app          ← 真正的业务代码
├── tests        ← 测试代码
├── alembic      ← 数据库迁移
├── scripts      ← 工具脚本
│
├── pyproject    ← 项目配置
├── uv.lock      ← 依赖版本锁定
├── .env         ← 环境变量
├── Dockerfile   ← Docker 镜像
└── README       ← 项目说明
```

---

## 四、app：真正的 Python 后端

最核心的是 `app/`，所有 Python 应用代码基本都在这里。

我们再把它拆成：

```
app/
│
├── api/
├── modules/
├── ai/
├── infrastructure/
├── models/
├── schemas/
├── tasks/
├── common/
├── config/
└── main.py
```

这几个目录其实代表了**不同的职责**。

---

## 五、main.py：程序启动入口

`app/main.py` 是整个 FastAPI 应用的入口。

逻辑非常简单：

```
启动项目
   ↓
创建 FastAPI
   ↓
加载配置
   ↓
初始化数据库
   ↓
初始化 Redis
   ↓
注册 API Router
   ↓
注册异常处理
   ↓
启动应用
```

也就是说：`main.py` **不是业务代码**，它更像整个系统的**启动器**。

---

## 六、api：API 总入口

```
app/api/
├── router.py
└── dependencies.py
```

这里有一个非常重要的区别。

### 1. router.py

负责把各个业务模块的 API 汇总起来，例如：

```
/api/v1/auth
/api/v1/users
/api/v1/chat
/api/v1/knowledge-bases
/api/v1/tickets
```

最终由 `app/api/router.py` 把这些 Router 注册进去。

可以理解成：

```
总路由
   │
   ├── Auth Router
   ├── User Router
   ├── Chat Router
   ├── Knowledge Router
   └── Ticket Router
```

### 2. dependencies.py

这里放 FastAPI 的依赖注入，例如：

```
get_db()
get_redis()
get_current_user()
get_current_tenant()
get_chat_service()
get_knowledge_service()
```

所以 `api/` 主要负责：**API 层公共入口 + 依赖注入。**

---

## 七、modules：真正的业务模块

这是整个工程结构里最重要的设计。

我们不采用 `service/ repository/ domain/ router/` 这种**全局分层**，而采用：

```
modules/
├── auth/
├── user/
├── chat/
├── knowledge/
└── ticket/
```

也就是：**按业务模块组织代码。**

**为什么？**

假设以后项目有 100 个 Service、200 个 Repository、300 个 API。如果全部放一起：

```
service/
    user_service.py
    chat_service.py
    ticket_service.py
    knowledge_service.py
    ...

repository/
    user_repository.py
    chat_repository.py
    ticket_repository.py
    ...
```

项目越来越大以后非常难维护。

所以我们采用：

```
modules/
│
├── user/
├── chat/
├── knowledge/
└── ticket/
```

每个模块自己管理自己的代码。这就是**模块化单体**。

---

## 八、一个业务模块内部怎么组织？

例如 `modules/chat/`：

```
chat/
├── router.py
├── schemas.py
├── service.py
├── domain/
└── repository/
```

这其实就是我们之前讲的：

```
Router
Service
Domain
Repository
```

---

## 九、Router：接收 HTTP 请求

例如 `modules/chat/router.py` 负责：

```
HTTP Request
     ↓
Router
     ↓
参数解析
     ↓
调用 Service
     ↓
返回 Response
```

Router 不应该负责：

```
❌ SQL
❌ Redis
❌ Milvus
❌ Prompt
❌ LLM
❌ 复杂业务逻辑
```

它只负责：**HTTP 世界和业务世界之间的入口。**

---

## 十、Schema：API 数据结构

`modules/chat/schemas.py`，例如 `ChatRequest` / `ChatResponse`。

负责：

```
Request JSON
     ↓
Pydantic Schema
     ↓
参数校验
```

例如用户发来：

```json
{
    "conversation_id": 1001,
    "message": "退款多久到账？"
}
```

进入 `ChatRequest`，然后验证 `conversation_id` / `message`。

---

## 十一、Service：业务用例

`modules/chat/service.py` 是非常重要的一层。

例如 `ChatService` 负责：

```
用户发送问题
      ↓
创建消息
      ↓
调用 AI
      ↓
获取 AI 结果
      ↓
保存消息
      ↓
返回结果
```

所以 Service 的本质：**实现一个业务用例。**

例如 `ChatService.send_message()` 不是简单 `INSERT message`，而是：

```
发送消息
=
保存用户消息
+
调用 AI
+
处理 AI
+
保存 AI 消息
+
返回结果
```

---

## 十二、Domain：业务规则

例如 `modules/chat/domain/` 里面可能有：

```
conversation.py
message.py
```

Domain 负责真正属于业务本身的规则，例如：

- 会话是否关闭？
- 消息是否允许发送？
- 工单状态能不能从 A → B？
- 知识库是否允许删除？

这些规则不应该依赖 FastAPI / PostgreSQL / Redis / Milvus，所以 **Domain 尽量保持纯 Python**。

---

## 十三、Repository：数据访问抽象

例如：

```
modules/chat/repository/
├── conversation_repository.py
└── message_repository.py
```

Repository 负责：**从哪里拿数据、怎么保存数据。**

例如 `ConversationRepository` 可能有：

```
get_by_id()
create()
update()
list()
```

但它不应该负责"用户是否有权限 / AI 应该怎么回答 / 退款规则是什么"——这些属于 Service / Domain。

---

## 十四、五个核心业务模块

我们的系统暂时有：

```
modules/
│
├── auth/
├── user/
├── chat/
├── knowledge/
└── ticket/
```

分别代表：

| 模块 | 内容 |
|------|------|
| **Auth** | 注册、登录、JWT、身份认证 |
| **User** | 用户、角色、权限、租户 |
| **Chat** | 会话、消息、AI 对话、SSE |
| **Knowledge** | 知识库、文档、文档上传、文档解析、知识库管理 |
| **Ticket** | 工单、转人工、工单分配、工单状态 |

---

## 十五、AI：为什么单独拿出来？

这是这个项目非常重要的一点。

我们不能把 AI 代码全部塞进 ChatService，否则最后会变成：

```
ChatService
    ↓
Intent
    ↓
Agent
    ↓
RAG
    ↓
Milvus
    ↓
LLM
    ↓
Tool
    ↓
Redis
    ↓
各种 Prompt
```

最后 ChatService 会变成一个几千行的大文件。

所以：**单独建立 `app/ai/` AI 能力层。**

---

## 十六、AI 目录

```
ai/
├── router/
├── agent/
├── rag/
├── memory/
├── prompt/
├── llm/
└── tools/
```

注意：这里的 `ai/router/` 和 `modules/chat/router.py` **不是一个东西**。

---

## 十七、ai/router：AI 决策路由

它**不是 FastAPI Router**，而是 **AI 决策器**。

例如用户说"退款多久到账？"：

```
        ↓
AI Router
        ↓
判断：这是知识问题
        ↓
RAG
```

另外用户说"我的订单 12345 到哪里了？"：

```
        ↓
AI Router
        ↓
判断：这是实时业务问题
        ↓
Tool
        ↓
订单 API
```

所以：

```
FastAPI Router 解决：HTTP 请求去哪里。
AI Router 解决：AI 请求应该走哪条能力链路。
```

---

## 十八、Agent

`ai/agent/` 负责**复杂任务决策和执行**。

例如用户说"我的订单为什么还没到？"：

```
Agent：
识别意图
    ↓
需要订单信息
    ↓
调用订单 Tool
    ↓
拿到订单状态
    ↓
判断是否异常
    ↓
组织答案
```

Agent 不应该直接 `Agent → SQLAlchemy`，而是：

```
Agent
 ↓
Tool
 ↓
Business Service
 ↓
Repository
 ↓
Database
```

---

## 十九、RAG

`ai/rag/` 负责：

```
Query Rewrite
      ↓
Embedding
      ↓
Vector Search
      ↓
Keyword Search
      ↓
Hybrid Retrieval
      ↓
Rerank
      ↓
Context
```

例如"退款多久到账？"，最终通过 Milvus + 关键词检索 + Rerank 找到退款政策，然后交给 LLM。

---

## 二十、Memory

`ai/memory/` 负责：短期记忆 / 会话历史 / 上下文。

例如：

```
用户：我想退款
AI：可以，请问订单号？
用户：12345
AI：好的，我帮你查询订单 12345
```

第二句话必须知道"12345 = 上一轮提到的订单号"，这就是 **Memory** 的作用。

---

## 二十一、Prompt

`ai/prompt/` 负责：

```
System Prompt
RAG Prompt
Agent Prompt
Intent Prompt
```

并且未来要支持 Prompt Version，例如：

```
customer_service_v1
customer_service_v2
```

方便后期做 A/B Test / Prompt 优化 / 版本回滚。

---

## 二十二、LLM

`ai/llm/` 做统一抽象。我们的业务代码不应该到处写 `OpenAI(...)`，而应该：

```
ChatService
     ↓
AIApplication
     ↓
LLMClient
     ↓
具体模型
```

以后可以切换 OpenAI / Qwen / DeepSeek / Claude / 本地模型，而上层代码不用大改。

---

## 二十三、Tools

`ai/tools/` 放 Agent 可以调用的工具：

```
tools/
├── order_tool.py
├── ticket_tool.py
├── customer_tool.py
└── knowledge_tool.py
```

例如：

```
Agent
 ↓
OrderTool
 ↓
OrderService
 ↓
OrderRepository
 ↓
Database
```

所以 **Agent 不直接碰数据库**。

---

## 二十四、Infrastructure：外部技术实现

```
infrastructure/
├── database/
├── redis/
├── milvus/
├── mq/
├── storage/
└── llm/
```

这一层的核心思想：**所有"外部技术"都放这里。**

- **database**：SQLAlchemy / PostgreSQL / 数据库连接池 / 事务
- **redis**：Redis Client / Cache / Lock / Rate Limit / Session
- **milvus**：Milvus Client / Vector Search / Collection / Index
- **mq**：未来 RabbitMQ / Kafka / Redis Stream，负责异步消息
- **storage**：文件 / 图片 / PDF / 文档 / 对象存储（MinIO / S3 / OSS）
- **llm**：具体 LLM 厂商的技术实现（OpenAI Client / Qwen Client / DeepSeek Client）

> 注意区分：`infrastructure/llm/` 是具体厂商实现，而 `ai/llm/` 是业务侧统一接口。

---

## 二十五、models：数据库模型

`app/models/` 放 SQLAlchemy ORM Model，例如：

```
User
Conversation
Message
Document
DocumentChunk
Ticket
```

它描述的是：**数据库长什么样**。例如 `User` → `users` table。

---

## 二十六、schemas：公共数据结构

`app/schemas/` 放**跨模块共享**的 Schema。

但要注意：业务模块自己的 API Schema（如 `modules/chat/schemas.py`）优先放在模块内部；全局 `app/schemas/` 只放真正跨模块共享的 Schema。

---

## 二十七、tasks：异步任务

```
tasks/
├── document_tasks.py
├── embedding_tasks.py
└── cleanup_tasks.py
```

例如上传 PDF：

```
上传 PDF
   ↓
Document 创建
   ↓
发送 MQ
   ↓
Worker
   ↓
document_tasks
   ↓
解析
   ↓
Chunk
   ↓
Embedding
   ↓
Milvus
```

这里要特别区分两个概念：

- **Async/await**：解决单个请求中的异步 I/O，例如 `await db.execute()` / `await redis.get()` / `await llm.chat()`
- **Task / Worker**：解决不应该阻塞 HTTP 请求的后台工作，例如 PDF 解析 / Embedding / 批量导入 / 清理任务

---

## 二十八、common：公共基础能力

```
common/
├── exceptions/
├── response/
├── middleware/
├── logging/
└── utils/
```

- **exceptions**：BusinessException / AuthenticationException / AuthorizationException / NotFoundException
- **response**：统一 API 返回 `{ "code": 0, "message": "success", "data": {} }`
- **middleware**：Request ID / CORS / 日志 / 耗时统计
- **logging**：统一日志能力（request_id / user_id / conversation_id / event / duration / status）
- **utils**：只放真正通用的小工具

> 注意：common **绝对不能变成垃圾桶**。

---

## 二十九、config：配置管理

```
config/
├── settings.py
└── logging.py
```

采用 **.env + Pydantic Settings**，例如：

```
APP_ENV
DATABASE_URL
REDIS_URL
MILVUS_HOST
MILVUS_PORT
LLM_API_KEY
LLM_MODEL
```

业务代码不应该到处 `os.getenv(...)`，而应该统一走 `Settings`。

---

## 三十、tests：测试

```
tests/
├── unit/
├── integration/
└── conftest.py
```

- **unit**：测试单个组件——Domain / Service / Agent / RAG / 工具函数
- **integration**：测试多个组件一起工作——API + Database + Redis
- **conftest.py**：提供测试公共资源——测试数据库 / 测试客户端 / 测试用户 / 测试 Fixture

---

## 三十一、alembic：数据库迁移

`alembic/` 负责**数据库表结构版本管理**，例如：

```
V1 → 创建 users
V2 → 创建 conversations
V3 → 创建 messages
V4 → 增加 tenant_id
```

所以：

- **SQLAlchemy** 负责：Python 对象 ↔ 数据库表
- **Alembic** 负责：数据库结构版本变化

---

## 三十二、scripts：工程脚本

`scripts/` 放一些初始化数据 / 创建管理员 / 批量导入 / 开发环境初始化脚本，例如：

```
create_admin.py
seed_data.py
```

---

## 三十三、pyproject.toml

这是 Python 项目的核心配置文件之一，里面统一管理：

```
项目名称
Python版本
依赖
开发依赖
Ruff
Pytest
```

pyproject.toml 负责告诉项目："这个 Python 项目需要什么、怎么检查、怎么测试。"

---

## 三十四、uv.lock

我们使用 **uv** 管理 Python 环境和依赖。

关系：

```
pyproject.toml  → 声明依赖
uv              → 解析依赖
uv.lock         → 锁定最终版本
```

这样你的电脑 / 测试环境 / 服务器 / Docker，尽可能使用一致的依赖版本。

---

## 三十五、Ruff

代码质量工具，负责：**代码检查** 和 **代码格式化**。

```
uv run ruff check .
uv run ruff format .
```

---

## 三十六、Pytest

测试运行：`uv run pytest`，负责单元测试 / 集成测试。

---

## 三十七、logging

日志使用 **Python 标准 logging**，而不是 `print("用户登录了")`。

真实项目应该记录 INFO / WARNING / ERROR，例如：

```
request_id=abc123
user_id=1001
event=chat_request
duration=1.82
status=success
```

未来可以继续接 ELK / Loki / Grafana / OpenTelemetry。

---

## 三十八、Docker

项目提供 `Dockerfile` 用于 Python 应用。

后面还可以加入 `docker-compose.yml` 统一启动：

```
FastAPI
PostgreSQL
Redis
Milvus
MQ
```

---

## 三十九、整个工程真正的调用关系

现在把整个结构串起来。

**一次普通请求：**

```
Client
   ↓
Nginx
   ↓
FastAPI
   ↓
modules/chat/router.py
   ↓
ChatService
   ↓
Domain
   ↓
Repository
   ↓
Infrastructure
   ↓
PostgreSQL
```

---

## 四十、AI 请求的调用关系

```
Client
   ↓
ChatRouter
   ↓
ChatService
   ↓
AI Application
   ↓
AI Router
   ↓
┌───────────────┬────────────────┐
│               │                │
RAG            Agent          Direct Answer
│               │
│               ↓
│             Tool
│               ↓
│          Business Service
│
↓
Milvus / Keyword Search

        ↓

      LLMClient

        ↓

       SSE

        ↓

      Client
```

---

## 四十一、知识库上传的调用关系

这个链路非常重要：

```
用户上传 PDF
       ↓
KnowledgeRouter
       ↓
KnowledgeService
       ↓
保存 Document
       ↓
提交异步任务
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
更新 Document Status
```

所以：**上传接口不应该一直等到 PDF 完成解析才返回。**

---

## 四十二、最终依赖方向

这是第八阶段最重要的架构规则之一。

我们规定：

```
Router
   ↓
Service
   ↓
Domain
   ↓
Repository
   ↓
Infrastructure
```

AI：

```
AI Application
   ↓
Agent / RAG
   ↓
AI Interface
   ↓
Infrastructure
```

业务和 AI：

```
ChatService
     ↓
AIApplication
```

而不是：

```
ChatRouter
 ↓
Agent
```

---

## 四十三、明确禁止的依赖

下面这些以后都不允许：

```
Router → PostgreSQL
Router → Redis
Router → Milvus

Domain → FastAPI
Domain → Redis
Domain → PostgreSQL

Agent → SQLAlchemy
Agent → PostgreSQL

Repository → Router
```

原因很简单：**每一层只负责自己的事情。**

---

## 四十四、最终你应该形成这个认知

以前你看到项目可能觉得 `router.py / service.py / repository.py / model.py` 都是一些 Python 文件。

现在应该理解成：

```
Router       = HTTP世界
Service      = 业务用例
Domain       = 业务规则
Repository   = 数据访问抽象
Infrastructure = 外部技术实现
AI           = AI能力
Task         = 后台异步工作
Common       = 跨模块公共能力
Config       = 系统配置
```

---

## 四十五、第八阶段最终成果

完成这一阶段后，我们应该得到：

```
① 项目目录结构
        ↓
② 业务模块划分
        ↓
③ Router / Service / Domain / Repository
        ↓
④ AI / Agent / RAG
        ↓
⑤ Infrastructure
        ↓
⑥ Database / Redis / Milvus / MQ
        ↓
⑦ Config
        ↓
⑧ Dependency Injection
        ↓
⑨ Exception
        ↓
⑩ Logging
        ↓
⑪ Testing
        ↓
⑫ Alembic
        ↓
⑬ uv + pyproject
        ↓
⑭ Ruff
        ↓
⑮ Docker
```

到这里，我们才真正拥有一个**可以开始写代码的企业级 Python AI 客服项目骨架**。

---

## 四十六、整个项目到目前为止

现在我们的开发顺序已经非常清楚：

```
第一阶段     PRD
↓
第二阶段     领域模型
↓
第三阶段     核心业务流程
↓
第四阶段     数据库 ER 模型
↓
第五阶段     数据库表结构
↓
第六阶段     系统架构
↓
第七阶段     API 接口设计
↓
第八阶段     项目工程结构     ← 现在
↓
第九阶段     核心类与接口设计
↓
第十阶段     项目初始化 + 基础设施
↓
第十一阶段   Auth / JWT / RBAC
↓
第十二阶段   用户与租户
↓
第十三阶段   Chat / Conversation / Message
↓
第十四阶段   RAG 知识库
↓
第十五阶段   Agent
↓
第十六阶段   Tool / Business API
↓
第十七阶段   SSE
↓
第十八阶段   异步任务 / MQ
↓
第十九阶段   Redis / 缓存 / 限流 / 锁
↓
第二十阶段   测试
↓
第二十一阶段 Docker / Nginx / Linux
↓
第二十二阶段 监控 / 日志 / Tracing
↓
第二十三阶段 性能与高并发
↓
第二十四阶段 部署上线
```

> 第八阶段的核心不是"记住目录"，而是理解：
> **一个真实企业级 Python 项目为什么要这么拆？每个目录解决什么问题？代码之间为什么这样调用？**

---

# 附录（合并自上一版 V1.0）：工程化基线明细

> 说明：以下内容来自第八阶段上一版文稿中的"补充：工程化基线"章节，保留以供查阅。

## A.1 工程基线总览

```
工程基线
├── uv          → Python 项目/依赖/环境管理
├── pyproject   → 项目统一配置入口
├── Ruff        → 代码检查 + 格式化
├── Pytest      → 单元测试
└── logging     → 标准日志
```

也就是：

```
开发环境
    ↓
uv
    ↓
pyproject.toml
    ↓
┌─────────────┬─────────────┬─────────────┐
│    Ruff     │   Pytest    │  logging    │
│ 代码质量    │   测试      │   日志      │
└─────────────┴─────────────┴─────────────┘
```

## A.2 uv：工程基线

正式使用 uv，负责 Python 版本 / 虚拟环境 / 依赖安装 / 依赖锁定 / 项目运行。以后不再以 `pip install ...` 作为项目主要依赖管理方式。

```
项目初始化：uv init
创建环境：uv venv

安装依赖：
uv add fastapi
uv add sqlalchemy
uv add asyncpg
uv add redis
uv add pydantic-settings

开发依赖：
uv add --dev pytest
uv add --dev ruff
```

## A.3 pyproject.toml 示例

`pyproject.toml` 是整个项目的工程配置中心，统一管理项目元信息 / Python 版本 / 生产依赖 / 开发依赖 / Ruff 配置 / Pytest 配置：

```toml
[project]
name = "enterprise-ai-customer-service"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    "fastapi",
    "sqlalchemy",
    "asyncpg",
    "redis",
    "pydantic-settings",
]

[dependency-groups]
dev = [
    "pytest",
    "ruff",
]
```

## A.4 工程化工具清单

| 工具 | 职责 |
|------|------|
| uv | Python 环境、依赖、项目管理 |
| pyproject.toml | 项目统一工程配置 |
| uv.lock | 锁定依赖版本 |
| Ruff | Lint + Format |
| Pytest | 单元测试 / 集成测试 |
| logging | 标准日志 |
| Alembic | 数据库迁移 |
| Git | 版本控制 |
| Docker | 运行环境标准化 |

## A.5 开发闭环

```
                    Git
                     │
                     ▼
                  开发代码
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
        Ruff                  Pytest
     代码质量                 测试
          │                     │
          └──────────┬──────────┘
                     ▼
                  FastAPI
                     │
             ┌───────┴───────┐
             ▼               ▼
          logging         数据库
                             │
                           Alembic
```

而 uv 负责整个 Python 项目的环境 + 依赖 + 运行。
