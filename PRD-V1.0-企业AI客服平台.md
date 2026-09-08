# 《企业 AI 客服平台》PRD V1.0

> 项目代号：AI Customer Service Platform
> 业务类型：SaaS 企业
> 产品形态：企业级 AI 客服 + 人工客服协同平台
> 第一阶段目标：企业版
> 后续目标：生产级平台

---

## 一、产品背景

假设我们是一家 SaaS 公司，向企业客户提供一套在线软件平台。

客户在使用过程中会产生大量问题：

- 产品怎么使用？
- 账号为什么登录不了？
- 我的套餐什么时候到期？
- 怎么添加成员？
- 怎么申请退款？
- 我的订单是什么状态？
- 这个功能在哪里？

**传统模式：**

```
客户
 ↓
人工客服
 ↓
客服查文档
 ↓
客服查数据库
 ↓
客服回复
```

**问题是：**

- 大量重复问题消耗客服人力
- 客服需要在多个系统之间查询
- 新客服需要学习大量产品知识
- 客服响应速度不稳定
- 复杂问题需要人工处理
- 企业知识无法被充分利用

所以我们设计：**一个 AI + 人工协同的企业客服平台。**

---

## 二、产品目标

核心目标不是：

> "让 AI 聊天。"

而是：

> 让 AI 尽可能自动解决客户问题，解决不了时无缝交给人工客服。

最终形成：

```
                    客户问题
                       ↓
                  AI 客服接待
                       ↓
                 理解用户意图
                       ↓
             ┌─────────┼─────────┐
             ↓         ↓         ↓
           知识库     业务系统    人工客服
            RAG       Tool       Human
             ↓         ↓         ↓
             └─────────┼─────────┘
                       ↓
                    最终解决
```

---

## 三、用户角色

我们第一版定义 4 类角色。

### 1. Customer —— 企业客户

使用 AI 客服解决问题。

能够：

- 注册
- 登录
- 创建会话
- 发送消息
- 查看 AI 回复
- 查看历史会话
- 查询自己的业务信息
- 创建工单
- 申请人工客服

### 2. AI —— AI 客服

AI 不是普通聊天机器人。

它需要：

```
理解问题
 ↓
判断意图
 ↓
决定解决方式
 ↓
调用知识库 / 业务工具
 ↓
生成答案
 ↓
判断是否解决
 ↓
必要时转人工
```

### 3. Agent —— 人工客服

人工客服负责处理：

- AI 无法解决的问题
- 复杂业务问题
- 客户投诉
- 特殊情况
- 需要人工审批的问题

客服可以：

- 查看客户
- 查看客户历史会话
- 接管 AI 会话
- 回复客户
- 查看订单
- 创建工单
- 关闭工单

### 4. Admin —— 管理员

负责管理整个系统：

- 用户
- 客服
- 角色
- 权限
- 知识库
- AI 配置
- 系统配置
- 业务数据

---

## 四、核心产品模块

整个系统暂时划分为 **8 个模块**。

```
企业 AI 客服平台
│
├── 1. 用户与权限
├── 2. 客户管理
├── 3. 会话管理
├── 4. 工单管理
├── 5. AI 客服
├── 6. 企业知识库
├── 7. Agent / Tool
└── 8. 管理后台
```

**后面生产版再增加：**

```
├── 9. 多租户
├── 10. 消息中心
├── 11. AI Evaluation
├── 12. 成本管理
└── 13. Observability
```

---

## 五、模块 1：用户与权限

**用户接口：**

```
POST /auth/register
POST /auth/login
POST /auth/logout
GET  /users/me
```

**登录流程：**

```
账号密码
   ↓
验证
   ↓
JWT
   ↓
客户端
   ↓
后续请求携带 Token
```

**权限矩阵：**

| 角色 | 权限范围 |
|------|----------|
| **Admin** | 用户管理、客服管理、知识库管理、系统配置 |
| **Agent** | 查看客户、查看会话、回复消息、管理工单 |
| **Customer** | 创建会话、发送消息、查看自己的数据 |

权限树：

```
Admin
 │
 ├── 用户管理
 ├── 客服管理
 ├── 知识库管理
 └── 系统配置

Agent
 │
 ├── 查看客户
 ├── 查看会话
 ├── 回复消息
 └── 管理工单

Customer
 │
 ├── 创建会话
 ├── 发送消息
 └── 查看自己的数据
```

这里以后就会真正使用：

- JWT
- RBAC
- FastAPI Dependency
- Middleware

---

## 六、模块 2：客户管理

客服可以查看：

```
客户
 ├── 基本信息
 ├── 注册时间
 ├── 当前套餐
 ├── 套餐到期时间
 ├── 历史会话
 └── 工单
```

**示例：**

```
Customer
------------------
姓名：张三
公司：ABC科技
套餐：Professional
到期：2026-12-31
会话数：32
工单数：4
```

---

## 七、模块 3：会话系统

这是整个系统的核心。

**一个会话：**

```
Conversation
    │
    ├── Message
    ├── Message
    ├── Message
    └── Message
```

**示例对话：**

> **Customer**：
> "我的套餐什么时候到期？"
>
> **AI**：
> "您的 Professional 套餐将在 2026-12-31 到期。"

**会话状态流转：**

```
AI处理中
   ↓
AI已解决
```

或者：

```
AI处理中
   ↓
需要人工
   ↓
人工处理中
   ↓
人工解决
   ↓
会话关闭
```

---

## 八、模块 4：工单系统

如果问题无法通过聊天解决：

```
AI
 ↓
创建工单
 ↓
分配客服
 ↓
客服处理
 ↓
解决
 ↓
关闭
```

**工单字段：**

```
Ticket
 ├── ID
 ├── Customer
 ├── Conversation
 ├── Title
 ├── Description
 ├── Priority
 ├── Status
 ├── Assignee
 └── CreatedAt
```

**状态流转：**

```
OPEN
 ↓
ASSIGNED
 ↓
PROCESSING
 ↓
RESOLVED
 ↓
CLOSED
```

---

## 九、模块 5：AI 客服

这里开始进入真正的 AI。

**示例：** 用户问"怎么创建团队？"

```
用户问题
 ↓
ChatService
 ↓
AI
 ↓
判断：这是产品使用问题
 ↓
查询知识库
 ↓
RAG
 ↓
LLM
 ↓
回答
```

---

## 十、AI 不是什么都调用 LLM

这一点非常重要。

我们以后设计成：

```
                    User Query
                        ↓
                 Query Understanding
                        ↓
               Intent / Classification
                        ↓
          ┌─────────────┼─────────────┐
          ↓             ↓             ↓
       Knowledge      Business       Human
        Question       Query         Service
          ↓             ↓             ↓
         RAG           Tool         Transfer
          ↓             ↓             ↓
          └─────────────┼─────────────┘
                        ↓
                       LLM
                        ↓
                     Answer
```

**路由示例：**

| 问法 | 类型 | 走法 |
|------|------|------|
| "怎么创建团队？" | 知识问 | RAG |
| "我的套餐什么时候到期？" | 实时数据 | Tool → MySQL |
| "帮我创建一个售后工单。" | 要执行操作 | Agent → `create_ticket()` → MySQL |
| "我要投诉你们公司。" | AI 无法解决 | Agent → Human Handoff → 人工客服 |

---

## 十一、模块 6：企业知识库

**管理员可以上传：**

- PDF
- Word
- Markdown
- 产品文档

**入库流程：**

```
Document
 ↓
解析
 ↓
清洗
 ↓
Chunk
 ↓
Embedding
 ↓
Vector DB
```

**查询流程：**

```
用户问题
 ↓
Embedding
 ↓
Vector Search
 ↓
Milvus
 ↓
候选文档
 ↓
Reranker
 ↓
Top-K
 ↓
LLM
```

**后续升级（Hybrid Search）：**

```
             Query
               ↓
       ┌───────┴────────┐
       ↓                ↓
    Vector             BM25
       ↓                ↓
       └───────┬────────┘
               ↓
             RRF
               ↓
           Reranker
               ↓
             Top-K
               ↓
              LLM
```

---

## 十二、模块 7：Agent + Tool

这是整个项目最有价值的部分之一。

**业务 Tool 清单：**

- `get_customer()`
- `get_subscription()`
- `get_order()`
- `get_ticket()`
- `create_ticket()`
- `get_product_info()`
- `handoff_to_human()`

**示例：** 用户问"我的套餐还有多久到期？"

```
User Query
    ↓
Agent
    ↓
LLM
    ↓
需要实时业务数据
    ↓
get_subscription()
    ↓
MySQL
    ↓
返回数据
    ↓
LLM
    ↓
最终答案
```

---

## 十三、复杂任务

例如用户说：

> "帮我看看我的套餐什么时候到期，如果已经过期就帮我创建一个工单。"

这时候 Agent：

```
                  User
                   ↓
                 Agent
                   ↓
            get_subscription()
                   ↓
             判断套餐状态
              ↙          ↘
          未过期          已过期
             ↓              ↓
           回复        create_ticket()
                            ↓
                       Ticket Service
                            ↓
                          MySQL
                            ↓
                          回复
```

这就不再是：

```
用户 → LLM → 答案
```

而是：

```
用户
 ↓
Agent
 ↓
Planning
 ↓
Tool
 ↓
Business System
 ↓
Tool Result
 ↓
Agent
 ↓
Final Answer
```

---

## 十四、模块 8：管理后台

管理员可以看到：

```
Dashboard
│
├── 今日会话
├── AI解决率
├── 人工转接率
├── 平均响应时间
├── 工单数量
├── 知识库数量
└── AI Token 消耗
```

这一步会为后面的 **Metrics / Monitoring / Evaluation / 成本统计** 打基础。

---

## 十五、一个完整用户故事

我们用一个真实场景把整个系统串起来。

**客户：**
> "我的套餐什么时候到期？"

**Step 1：请求**

```
POST /api/v1/chat
```

**Step 2：Router —— ChatRouter**

接收：

```json
{
  "conversation_id": 1001,
  "message": "我的套餐什么时候到期？"
}
```

**Step 3：Service —— ChatService**

开始处理。

**Step 4：Agent**

```
Agent
 ↓
理解问题
 ↓
判断需要查询订阅信息
```

**Step 5：Tool**

```
get_subscription()
```

**Step 6：Repository**

```
SubscriptionRepository
```

**Step 7：MySQL —— `subscriptions`**

得到：`expires_at = 2026-12-31`

**Step 8：LLM**

把业务结果交给 LLM：

```
用户问题
+
业务数据
 ↓
LLM
```

**Step 9：Streaming**

```
LLM
 ↓
SSE
 ↓
Frontend
```

前端逐步显示：

```
您的
 ↓
您的 Professional
 ↓
您的 Professional 套餐
 ↓
您的 Professional 套餐将在
 ↓
您的 Professional 套餐将在 2026-12-31 到期。
```

---

## 十六、另一个完整故事：知识库

**客户：** "怎么创建团队？"

**系统判断：这是知识问题。**

于是：

```
Query
 ↓
Hybrid Retrieval
 ↓
Milvus + BM25
 ↓
Reranker
 ↓
Context
 ↓
LLM
 ↓
SSE
 ↓
用户
```

---

## 十七、第三个故事：人工转接

**客户：** "我要投诉，我要求退款。"

**AI 处理：**

```
理解问题
 ↓
判断：可能涉及人工处理
 ↓
询问必要信息
 ↓
仍然无法解决
 ↓
handoff_to_human()
```

**然后：**

```
AI
 ↓
创建人工客服任务
 ↓
客服工作台
 ↓
客服接管会话
 ↓
人工回复
```

---

## 十八、我们的核心业务闭环

所以整个产品实际上只有一个非常重要的闭环：

```
                     用户
                      ↓
                    提问
                      ↓
                AI 理解问题
                      ↓
              判断解决路径
                      ↓
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
       RAG           Tool         Human
        ↓             ↓             ↓
     知识回答       业务查询       人工处理
        ↓             ↓             ↓
        └─────────────┼─────────────┘
                      ↓
                   解决问题
                      ↓
                   会话结束
```

**这就是整个项目的核心业务骨架。**

---

## 十九、第一阶段暂时不做什么

为了避免项目无限膨胀，V1～V6 暂时不做：

- ❌ 多租户
- ❌ 多模态
- ❌ 语音客服
- ❌ 视频客服
- ❌ 复杂 Multi-Agent
- ❌ 自动模型训练
- ❌ Fine-tuning
- ❌ 大规模分布式微服务

这些以后可以作为生产版升级。

---

## 二十、项目最终技术地图

我们最后会得到这样一张技术图：

```
                    企业 AI 客服平台
                           │
             ┌─────────────┴─────────────┐
             ↓                           ↓
        传统后端系统                    AI 系统
             │                           │
         FastAPI                         LLM
             │                           │
         Router                          Prompt
             │                           │
         Service                       Agent
             │                           │
         Domain                         Tool
             │                           │
       Repository                     Memory
             │                           │
          MySQL                         RAG
             │                           │
          Redis                  ┌───────┴───────┐
             │                   ↓               ↓
        JWT / RBAC            Milvus           BM25
             │                   ↓               ↓
             │                   └───────┬───────┘
             │                           ↓
             │                       Reranker
             │                           ↓
             │                          LLM
             │
             └──────────────┬────────────┘
                            ↓
                         Async
                            ↓
                           MQ
                            ↓
                         Worker
                            ↓
                         Docker
                            ↓
                         CI/CD
                            ↓
                  Logging / Metrics / Tracing
```

---

## 二十一、现在 PRD 还差最后一个非常重要的东西

我们已经确定了：

- 谁使用
- 为什么使用
- 有哪些角色
- 有哪些模块
- AI 怎么工作

**下一步不能直接写代码。**

真实项目接下来要做：

> **业务领域模型 + 核心业务流程 + 数据模型。**

也就是回答：

- `Customer`
- `Conversation`
- `Message`
- `Order`
- `Subscription`
- `Ticket`
- `KnowledgeBase`
- `Document`
- `Chunk`
- `AgentTask`
- `Tool`

这些东西之间到底是什么关系？

例如：

```
一个 Customer
 ↓
可以有多个 Conversation

一个 Conversation
 ↓
有多个 Message

一个 Conversation
 ↓
可能产生一个 Ticket

一个 KnowledgeBase
 ↓
有多个 Document

一个 Document
 ↓
拆成多个 Chunk
```

这一步非常关键，因为它会直接决定后面的：

```
Domain
↓
MySQL 表
↓
SQLAlchemy Model
↓
Repository
↓
Service
↓
API
```
