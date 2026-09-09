# 《企业 AI 客服平台》完整开发路线（项目总施工图）V1.0

> 前文：PRD V1.0 → 领域模型设计 → 核心业务流程设计 → 数据库 ER 模型设计（均已产出独立文档）

## 总目标

> 从 PRD 开始，最终做成一个**企业级、可部署、可监控、具备 RAG + Agent 能力**的 AI 客服平台。

整个项目的施工图铺开，后面就严格按照这个顺序推进。

---

## 完整开发路线（22 个阶段）

```
第 1 阶段  PRD
     ↓
第 2 阶段  领域模型
     ↓
第 3 阶段  核心业务流程
     ↓
第 4 阶段  数据库 ER 模型
     ↓
第 5 阶段  数据库表结构
     ↓
第 6 阶段  系统架构设计
     ↓
第 7 阶段  API 接口设计
     ↓
第 8 阶段  项目工程结构
     ↓
第 9 阶段  V1：基础后端
     ↓
第 10 阶段 V2：数据库
     ↓
第 11 阶段 V3：认证与权限
     ↓
第 12 阶段 V4：Redis + 异步
     ↓
第 13 阶段 V5：LLM + AI Chat
     ↓
第 14 阶段 V6：RAG 知识库
     ↓
第 15 阶段 V7：Agent + Tool
     ↓
第 16 阶段 V8：人工客服协同
     ↓
第 17 阶段 V9：消息队列 / Worker
     ↓
第 18 阶段 V10：测试与工程化
     ↓
第 19 阶段 V11：Docker + Nginx + CI/CD
     ↓
第 20 阶段 V12：日志 / 监控 / Tracing
     ↓
第 21 阶段 V13：AI Evaluation
     ↓
第 22 阶段 V14：生产级优化
```

---

## 第一阶段：PRD 产品需求设计

**目标：** 明确"我们到底要做什么"。

**完成：**

- 产品背景
- 产品目标
- 用户角色
- 功能模块
- 用户故事
- 核心场景
- 业务边界
- V1 → V14 产品演进

**最终产物：** PRD V1.0

> 我们现在就在这里。（注：已产出 `PRD-V1.0-企业AI客服平台.md`）

---

## 第二阶段：领域模型设计

**目标：** 明确"系统里到底有哪些业务对象"。

**确定：**

```
User
Customer
Conversation
Message
Ticket
Subscription
KnowledgeBase
Document
Chunk
AgentTask
Tool
Role
Permission
```

并明确：

- 每个对象负责什么
- 不负责什么
- 对象之间是什么关系

**最终产物：** 领域模型

> 这一阶段我们已经基本完成。（注：已产出 `企业AI客服平台-领域模型设计-V1.0.md`）

---

## 第三阶段：核心业务流程设计

**目标：** 把业务真正跑通。

重点设计 5 条链路：

```
① 注册 → 登录 → JWT → 进入系统

② 客户 → AI → RAG → 回答

③ 客户 → Agent → Tool → MySQL → 回答

④ AI → 转人工 → Ticket → 客服

⑤ 文档 → Chunk → Embedding → Vector DB
```

同时定义：

- 正常流程
- 异常流程
- 状态变化

**最终产物：**

- 业务流程图
- 时序流程
- 状态机

> 注：已产出 `企业AI客服平台-核心业务流程设计-V1.0.md`（42 节）。

---

## 第四阶段：数据库 ER 模型设计

**目标：** 把业务对象变成数据库关系。

例如：

```
Customer
   │
   ├── Conversation
   │       └── Message
   │
   ├── Subscription
   │
   └── Ticket

KnowledgeBase
   └── Document
          └── Chunk
```

重点确定：

- 1:N
- N:N
- 外键
- 主键
- 关联关系

**最终产物：** ER Diagram

> 注：已产出 `企业AI客服平台-数据库ER模型设计-V1.0.md`（32 节，14 张核心表）。

---

## 第五阶段：数据库表结构设计

**目标：** 真正确定 MySQL 怎么存数据。

例如：

```
users
roles
permissions
customers
conversations
messages
tickets
subscriptions
knowledge_bases
documents
chunks
agent_tasks
```

确定：

- 字段
- 类型
- 索引
- 唯一约束
- 外键
- 状态字段
- 时间字段
- 软删除

**最终产物：**

- MySQL Schema
- SQLAlchemy Models 设计

---

## 第六阶段：系统架构设计

**目标：** 决定代码应该怎么组织。

确定：

```
Router
Service
Domain
Repository
Infrastructure
Common
```

以及：

```
LLM
RAG
Agent
Redis
MySQL
Milvus
MQ
Object Storage
```

最终形成：

```
请求
 ↓
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

同时设计：

- AI 请求怎么走
- RAG 怎么走
- Agent 怎么走
- 异步任务怎么走

---

## 第七阶段：API 接口设计

**目标：** 定义前后端怎么通信。

例如：

```
POST /auth/register
POST /auth/login

GET /customers
GET /customers/{id}

POST /conversations
GET /conversations

POST /conversations/{id}/messages

POST /tickets
GET /tickets

POST /knowledge-bases
POST /documents

POST /chat
```

确定：

- Request
- Response
- Path
- Query
- Body
- Status Code
- 错误码
- 鉴权
- 权限

**最终产物：**

- API Specification
- Swagger / OpenAPI

---

## 第八阶段：项目工程结构设计

**目标：** 正式建立代码骨架。

例如：

```
app/
├── api/
├── service/
├── domain/
├── repository/
├── infrastructure/
├── agent/
├── rag/
├── models/
├── schemas/
├── common/
├── config/
└── main.py
```

同时确定：

- 配置管理
- 依赖注入
- 异常处理
- 日志
- 数据库连接
- Redis 连接

---

## 第九阶段：V1 基础后端

**目标：** 先把普通后端跑起来。

**技术：**

- Python
- FastAPI
- Pydantic

**实现：**

- 健康检查
- 用户
- 客户
- 会话
- 消息
- 工单

**暂时：**

```
❌ AI
❌ RAG
❌ Agent
```

先把传统 API 跑通。

---

## 第十阶段：V2 数据库

加入：

```
MySQL
SQLAlchemy
Alembic
```

完成：

- Model
- Session
- CRUD
- Repository
- Transaction
- Migration

最终：

```
FastAPI
 ↓
Service
 ↓
Repository
 ↓
SQLAlchemy
 ↓
MySQL
```

---

## 第十一阶段：V3 认证与权限

加入：

```
JWT
RBAC
Password Hash
Authentication
Authorization
```

完成：

- 注册
- 登录
- Token
- 用户身份
- 角色
- 权限
- 接口保护

最终实现：

```
JWT = 我是谁
RBAC = 我能干什么
```

---

## 第十二阶段：V4 Redis + 异步

加入：

```
Redis
asyncio
Background Task
```

实现：

- 缓存
- Session
- 限流
- 分布式锁
- 验证码 / 临时数据

并开始处理：

- 异步数据库
- 异步 Redis
- 异步 HTTP
- LLM 调用

---

## 第十三阶段：V5 LLM + AI Chat

第一次正式接入大模型。

实现：

- LLM Client
- Prompt
- Chat Service
- Conversation Context
- Streaming
- SSE

链路：

```
用户
 ↓
FastAPI
 ↓
ChatService
 ↓
LLM
 ↓
SSE
 ↓
前端
```

这一阶段先做：**普通 AI Chat。**

---

## 第十四阶段：V6 RAG 知识库

加入：

```
Document Parser
Chunk
Embedding
Milvus
Elasticsearch / BM25
Hybrid Search
Reranker
```

完成入库：

```
上传文档
 ↓
解析
 ↓
Chunk
 ↓
Embedding
 ↓
Vector DB
```

查询：

```
用户问题
 ↓
Hybrid Retrieval
 ↓
Rerank
 ↓
Context
 ↓
LLM
 ↓
答案
```

这阶段真正完成：**企业 AI 知识库。**

---

## 第十五阶段：V7 Agent + Tool

开始进入 Agent。

实现：

```
Agent
Tool
Tool Calling
Agent Loop
State
Task
```

工具：

```
get_customer()
get_subscription()
get_ticket()
create_ticket()
search_knowledge()
handoff_to_human()
```

实现：

```
用户
 ↓
Agent
 ↓
LLM
 ↓
选择 Tool
 ↓
Tool
 ↓
业务系统
 ↓
Tool Result
 ↓
LLM
 ↓
答案
```

---

## 第十六阶段：V8 AI + 人工客服协同

解决：**AI 解决不了怎么办？**

实现：

- AI Handoff
- Ticket
- Agent Assignment
- Human Takeover
- Conversation Transfer

形成：

```
AI
 ↓
判断无法解决
 ↓
创建 Ticket
 ↓
分配客服
 ↓
人工接管
 ↓
人工回复
 ↓
问题解决
```

> 到这里，产品才真正成为 **AI 客服平台，而不是 AI Chat Demo**。

---

## 第十七阶段：V9 消息队列 + Worker

解决耗时任务：

- PDF 解析
- Embedding
- 批量导入
- AI 任务
- 通知
- 数据处理

加入：

```
MQ
Worker
Task
Retry
Dead Letter
```

形成：

```
API
 ↓
MQ
 ↓
Worker
 ↓
执行
 ↓
任务状态
```

---

## 第十八阶段：V10 测试与工程化

加入：

```
pytest
Unit Test
Integration Test
API Test
Mock
Fixture
```

同时：

- 统一异常
- 统一响应
- 配置管理
- 代码规范
- Git
- Branch
- Code Review

**目标：** 不是"代码能运行"，而是"代码可以维护"。

---

## 第十九阶段：V11 Docker + Nginx + CI/CD

把项目变成真正可部署的软件。

加入：

```
Docker
Docker Compose
Linux
Nginx
HTTPS
```

然后：

```
Git
 ↓
CI
 ↓
Test
 ↓
Build
 ↓
Docker Image
 ↓
Deploy
```

使用：Jenkins / GitHub Actions

---

## 第二十阶段：V12 Logging / Monitoring / Tracing

让我们知道：**系统到底发生了什么。**

**Logging：**

```
谁
什么时候
调用了什么
发生了什么
```

**Metrics：**

```
QPS
CPU
Memory
Latency
Error Rate
AI Token
```

**Tracing：**

```
Request
 ↓
FastAPI
 ↓
Service
 ↓
Redis
 ↓
RAG
 ↓
LLM
 ↓
Tool
 ↓
MySQL
```

最终建立：

```
Logs
Metrics
Tracing
Alert
```

---

## 第二十一阶段：V13 AI Evaluation

这一阶段是普通后端和 AI 后端非常明显的区别。

建立：

```
LLM Evaluation
RAG Evaluation
Agent Evaluation
Prompt Evaluation
```

指标：

```
Answer Accuracy
Faithfulness
Retrieval Recall
Retrieval Precision
Rerank Quality
Tool Success Rate
Agent Success Rate
Hallucination
```

让我们能够回答："这个 AI 到底好不好？"，而不是"我感觉回答还行。"

---

## 第二十二阶段：V14 生产级优化

最后进入真正的生产环境思维：

```
高并发
高可用
成本控制
模型路由
Fallback
限流
熔断
重试
幂等
缓存
数据安全
审计
```

最终可以进一步演进：

```
单体
 ↓
模块化单体
 ↓
服务拆分
 ↓
微服务
```

---

## 最终完整技术成长路线

你可以把整个项目记成这张图：

```
                         企业 AI 客服平台
                                │
              ┌─────────────────┴─────────────────┐
              ↓                                   ↓
          后端工程能力                          AI 能力
              │                                   │
       Python / FastAPI                         LLM
       HTTP / REST                              Prompt
       Pydantic                                 Streaming
       SQL                                      RAG
       MySQL                                    Embedding
       SQLAlchemy                               Vector DB
       Redis                                    Agent
       JWT / RBAC                               Tool
       Async                                    Workflow
              │                                   │
              └─────────────────┬─────────────────┘
                                ↓
                           工程化能力
                                │
                  Git / Test / Docker / CI/CD
                                │
                                ↓
                       生产系统能力
                                │
                Logging / Metrics / Tracing
                                │
                                ↓
                         AI Evaluation
                                │
                                ↓
                       Production AI
```

我们后面就严格按照这个顺序。

---

## 目前进度

```
✅ 第一阶段：PRD
✅ 第二阶段：领域模型
⬜ 第三阶段：核心业务流程
⬜ 第四阶段：ER 模型
⬜ 第五阶段：数据库表结构
⬜ 第六阶段：系统架构
⬜ 第七阶段：API
⬜ 第八阶段：工程结构
⬜ V1～V14 实现
```

**下一步就继续《第三阶段：核心业务流程设计》。**

这一阶段建议不要只画一张大图，而是把 **客户注册登录、AI→RAG、AI→Agent→Tool、AI→人工、知识库上传** 这 5 条链路逐条拆到"请求进来以后每一步发生什么"的程度。
