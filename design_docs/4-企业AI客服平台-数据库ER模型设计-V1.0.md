# 《企业 AI 客服平台》第四阶段：数据库 ER 模型设计 V1.0

> 前文：《企业 AI 客服平台》PRD V1.0 → 第二阶段：领域模型设计 → 第三阶段：核心业务流程设计

## 本阶段要解决的问题

这一阶段我们正式进入数据库设计。

但有一个原则一定要记住：

> 不是"我知道 MySQL，所以我要建几张表"。
>
> 而是：**业务流程 → 业务对象 → 对象关系 → ER 模型 → 表结构。**

我们现在就按照上一阶段的 5 条核心链路，一步一步反推。

---

## 一、先看整个数据库要解决什么问题

我们的企业 AI 客服系统，目前至少需要管理这些东西：

```
用户体系
├── Tenant
├── User
├── Role
└── Permission

客服会话
├── Conversation
└── Message

人工客服
├── Ticket
├── TicketAssignment
└── TicketMessage

企业知识库
├── KnowledgeBase
├── Document
└── DocumentChunk

业务数据
└── Order
```

**注意：Milvus 不属于 MySQL 的核心业务表。**

- MySQL 管：谁 / 什么企业 / 什么会话 / 什么消息 / 什么工单 / 什么文档 / 什么 Chunk
- Milvus 管：Chunk 的向量 / Embedding / 向量检索

---

## 二、先从"企业"开始，而不是 User

这是企业级项目和普通 Todo 项目很大的区别。

普通项目可能 `User` 就够了。

但是企业 AI 客服通常是：

```
企业 A
 ├── 用户
 ├── 客服
 ├── 管理员
 └── 知识库

企业 B
 ├── 用户
 ├── 客服
 ├── 管理员
 └── 知识库
```

所以需要：**Tenant**

---

## 三、Tenant：企业租户

可以理解为：

> 一个企业 = 一个 Tenant

例如：

```
Tenant
----------------
id
name
status
created_at
updated_at
```

数据：

```
1 | 小米科技
2 | 华为科技
3 | 某某电商
```

于是：

```
Tenant
   │
   ├── User
   ├── Conversation
   ├── Ticket
   ├── KnowledgeBase
   └── Order
```

这就是**多租户**。

---

## 四、User：用户

用户表：

```
User
----------------
id
tenant_id
username
password_hash
nickname
status
created_at
updated_at
```

关系：

```
Tenant
   │
   │ 1:N
   ▼
 User
```

意思：一个企业可以有很多用户。

例如：

```
Tenant：ABC公司
       │
       ├── 张三
       ├── 李四
       ├── 王五
       └── 客服001
```

---

## 五、Role：角色

企业系统不能只有 User。

因为：

```
张三 → 普通客户
客服001 → 客服
管理员001 → 管理员
```

所以：

```
Role
----------------
id
tenant_id
name
code
created_at
```

例如：

```
customer
agent
admin
```

---

## 六、Permission：权限

```
Permission
----------------
id
name
code
```

例如：

```
conversation:read
conversation:create

ticket:read
ticket:update
ticket:assign

knowledge:create
knowledge:update
knowledge:delete

user:read
user:update
```

---

## 七、User 和 Role 是什么关系？

一个用户可以拥有多个角色：

```
张三
 ├── customer
 └── vip_customer
```

一个角色也可以属于多个用户：

```
customer
 ├── 张三
 ├── 李四
 ├── 王五
 └── ...
```

所以：

```
User
  │
  │ N:M
  ▼
Role
```

**数据库不能直接画 `User ←→ Role`**，而需要一个中间表：

```
UserRole
----------------
user_id
role_id
```

于是：

```
User
 │
 │ 1:N
 ▼
UserRole
 ▲
 │ N:1
 │
Role
```

---

## 八、Role 和 Permission

同样：

```
Role
 │
 │ N:M
 ▼
Permission
```

需要：

```
RolePermission
----------------
role_id
permission_id
```

例如：

```
admin
 ↓
RolePermission
 ↓
user:read
user:update
ticket:read
ticket:update
knowledge:create
knowledge:delete
```

所以完整权限模型：

```
User
 │
 ▼
UserRole
 │
 ▼
Role
 │
 ▼
RolePermission
 │
 ▼
Permission
```

这就是我们之前讲的：

```
JWT = 你是谁
RBAC = 你能做什么
```

JWT 解决身份，RBAC 解决权限。

---

## 九、Conversation：会话

现在进入 AI 客服核心业务。

一个客户可能：第一次咨询、第二次咨询、第三次咨询……每一次客服对话可以形成一个 `Conversation`。

```
Conversation
----------------
id
tenant_id
user_id
status
title
created_at
updated_at
```

关系：

```
User
 │
 │ 1:N
 ▼
Conversation
```

意思：一个用户可以拥有多个会话。

---

## 十、Message：消息

Conversation 里面会有很多消息：

```
Conversation
 │
 ├── Message
 ├── Message
 ├── Message
 ├── Message
 └── Message
```

所以：

```
Conversation
    │
    │ 1:N
    ▼
 Message
```

Message：

```
Message
----------------
id
conversation_id
sender_type
sender_id
content
message_type
created_at
```

例如：

```
sender_type = user
"我的订单什么时候到？"
```

然后：

```
sender_type = assistant
"您的订单预计明天送达。"
```

---

## 十一、为什么 Message 不直接放 Conversation？

**错误设计：**

```
Conversation
----------------
id
user_message
ai_message
...
```

因为一场聊天可能有：100 条、1000 条、10000 条。

所以必须：

```
Conversation
      │
      ▼
   Message
      │
      ├── 1
      ├── 2
      ├── 3
      ├── 4
      └── ...
```

这就是典型的：**一对多（1:N）**。

---

## 十二、Ticket：人工工单

当 AI 无法解决：

```
Conversation
     │
     ▼
   Ticket
```

Ticket：

```
Ticket
----------------
id
tenant_id
conversation_id
user_id
title
description
status
priority
created_at
updated_at
resolved_at
```

例如：

```
id: 10001

title:
商品损坏要求赔偿

status:
OPEN

priority:
HIGH
```

---

## 十三、Conversation 和 Ticket 的关系

这里需要思考一个业务问题：**一次 Conversation 可以产生几个 Ticket？**

实际企业系统里通常不能简单假设永远 1:1。

例如：

```
Conversation #001
       │
       ├── Ticket #100
       │
       └── Ticket #101
```

所以设计成：

```
Conversation
     │
     │ 1:N
     ▼
   Ticket
```

比较灵活。

---

## 十四、TicketAssignment：工单分配

工单创建以后：

```
Ticket
   ↓
分配客服
```

例如：

```
Ticket #10001
     ↓
客服001
```

**我们不建议直接把所有分配逻辑塞进 Ticket。**

可以设计：

```
TicketAssignment
----------------
id
ticket_id
agent_id
assigned_at
unassigned_at
```

这样以后可以记录：

```
Ticket
 ↓
客服001
 ↓
客服002
 ↓
客服003
```

完整历史都能保留。

---

## 十五、TicketMessage

人工客服处理的时候，也可能产生消息：

```
客户
 ↓
Ticket
 ↓
客服
 ↓
回复
```

所以可以有：

```
TicketMessage
----------------
id
ticket_id
sender_id
sender_type
content
created_at
```

**不过这里有一个重要设计：**

> 第一版可以不单独做 TicketMessage。

因为我们的核心聊天已经有：

```
Conversation
 ↓
Message
```

人工客服也可以继续使用 Conversation。那么：

```
Conversation
 │
 ├── 客户消息
 ├── AI消息
 ├── 客服消息
 └── 客服消息
```

Ticket 只负责："这个 Conversation 需要人工处理"。

这种设计其实更简单。

**所以我们 V1 可以采用：**

```
Conversation
      │
      ├── Message
      │
      └── Ticket
```

---

## 十六、KnowledgeBase：知识库

现在进入 RAG。

一个企业可以有多个知识库：

```
Tenant
 │
 ├── 售后知识库
 ├── 产品知识库
 └── FAQ知识库
```

所以：

```
KnowledgeBase
----------------
id
tenant_id
name
description
status
created_at
updated_at
```

关系：

```
Tenant
 │
 │ 1:N
 ▼
KnowledgeBase
```

---

## 十七、Document：文档

知识库下面有很多文档：

```
售后知识库
 │
 ├── 退款政策.pdf
 ├── 售后政策.pdf
 ├── 退货规则.pdf
 └── VIP政策.pdf
```

所以：

```
KnowledgeBase
      │
      │ 1:N
      ▼
   Document
```

Document：

```
Document
----------------
id
knowledge_base_id
name
file_name
file_url
status
created_at
updated_at
```

---

## 十八、DocumentChunk：文档切片

一个 PDF：

```
Document
 │
 ├── Chunk 001
 ├── Chunk 002
 ├── Chunk 003
 ├── Chunk 004
 └── ...
```

所以：

```
Document
   │
   │ 1:N
   ▼
DocumentChunk
```

Chunk：

```
DocumentChunk
----------------
id
document_id
chunk_index
content
token_count
created_at
```

---

## 十九、Chunk 和 Milvus 怎么关联？

这是 AI 项目数据库设计中非常重要的一点。

**MySQL：**

```
DocumentChunk
----------------
id = 10001
content = "支持7天无理由退款"
```

**Embedding：**

```
[0.123, 0.542, -0.234, ...]
```

**Milvus：**

```
vector_id = 10001
vector = [...]
```

于是：

```
MySQL                         Milvus

Chunk ID 10001   ←──────→    Vector ID 10001
内容：退款政策                Embedding：[...]
```

> MySQL 保存业务数据和 Chunk 文本，Milvus 保存向量。
> 两边通过 `chunk_id` 建立逻辑关联。

---

## 二十、为什么不把 Vector 存 MySQL？

当然某些数据库可以存向量。

但是我们的项目明确采用：

```
MySQL
+
Milvus
```

那么职责就应该清楚：

```
MySQL = 业务数据库
Milvus = 向量数据库
```

不要让一个系统承担所有事情。

---

## 二十一、Order：订单

Agent Tool 需要查订单。

所以：

```
Order
----------------
id
tenant_id
user_id
order_no
status
total_amount
created_at
updated_at
```

关系：

```
User
 │
 │ 1:N
 ▼
Order
```

例如：

```
张三
 │
 ├── ORD10001
 ├── ORD10002
 └── ORD10003
```

Agent：

```
查询订单
 ↓
OrderService
 ↓
OrderRepository
 ↓
MySQL
```

---

## 二十二、现在把所有核心实体串起来

终于可以画第一版 ER 模型。

```
                         Tenant
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
         User            Role        KnowledgeBase
          │                │                │
          │                │                ▼
          │                │             Document
          │                │                │
          │                │                ▼
          │                │          DocumentChunk
          │                │
          │                ▼
          │           Permission
          │
          ├──────────── Order
          │
          │
          ▼
     Conversation
          │
          ├──────── Message
          │
          │
          └──────── Ticket
                       │
                       ▼
                TicketAssignment
```

中间权限关系：

```
User
 │
 ▼
UserRole
 │
 ▼
Role
 │
 ▼
RolePermission
 │
 ▼
Permission
```

---

## 二十三、把它整理成真正的 ER 图

```
┌──────────────┐
│    Tenant    │
│──────────────│
│ id           │
│ name         │
└──────┬───────┘
       │
       │ 1:N
       ▼
┌──────────────┐
│     User     │
│──────────────│
│ id           │
│ tenant_id FK │
│ username     │
│ password     │
└──────┬───────┘
       │
       ├───────────────┐
       │               │
       │ 1:N           │ 1:N
       ▼               ▼
┌──────────────┐  ┌──────────────┐
│ Conversation │  │    Order     │
│──────────────│  │──────────────│
│ id           │  │ id           │
│ tenant_id    │  │ tenant_id    │
│ user_id      │  │ user_id      │
│ status       │  │ order_no     │
└──────┬───────┘  │ status       │
       │          └──────────────┘
       │ 1:N
       ▼
┌──────────────┐
│   Message    │
│──────────────│
│ id           │
│ conversation │
│ sender_type  │
│ content      │
└──────────────┘

Conversation
       │
       │ 1:N
       ▼
┌──────────────┐
│    Ticket    │
│──────────────│
│ id           │
│ conversation │
│ user_id      │
│ status       │
│ priority     │
└──────┬───────┘
       │
       │ 1:N
       ▼
┌──────────────────┐
│ TicketAssignment │
│──────────────────│
│ id               │
│ ticket_id        │
│ agent_id         │
└──────────────────┘
```

知识库：

```
Tenant
  │
  │ 1:N
  ▼
KnowledgeBase
  │
  │ 1:N
  ▼
Document
  │
  │ 1:N
  ▼
DocumentChunk
  │
  └──────────────→ Milvus Vector
```

---

## 二十四、现在你要特别理解一个概念：FK

你之前学 SQLAlchemy 的时候经常看到：

```python
tenant_id = Column(ForeignKey("tenant.id"))
```

现在就非常容易理解了。

例如：

```
User
----------------
id
tenant_id
```

其中 `User.tenant_id` 就是 `Tenant.id` 的外键。

意思：**这个 User 属于哪个企业？**

---

## 二十五、为什么不用把 Tenant 名字直接放 User？

比如：

```
User
id
tenant_name = "ABC公司"
```

这是**不好**的。

因为：

- ABC 公司可能改名字
- 重复数据很多

应该：

```
User
tenant_id = 100
```

然后：

```
Tenant
id = 100
name = ABC公司
```

这就是数据库的**规范化思想**。

---

## 二十六、现在开始区分"实体"和"表"

这两个概念不要混淆。

我们现在讨论的是：

```
User
Conversation
Message
Ticket
Document
```

这些首先是**业务实体**，然后才映射成 `user / conversation / message / ticket / document` 数据库表。

所以正确思路：

```
业务实体
   ↓
领域模型
   ↓
持久化模型
   ↓
数据库表
```

而不是：

```
我要建表
 ↓
随便设计字段
```

---

## 二十七、现在回头看六层架构

这时候你应该已经开始看到它们之间的关系了。

**例如：用户注册**

```
AuthRouter
    ↓
AuthService
    ↓
User
    ↓
UserRepository
    ↓
SQLAlchemy
    ↓
MySQL
```

**查询订单**

```
ChatRouter
    ↓
ChatService
    ↓
Agent
    ↓
OrderTool
    ↓
OrderService
    ↓
OrderRepository
    ↓
SQLAlchemy
    ↓
MySQL
```

**RAG**

```
ChatRouter
    ↓
ChatService
    ↓
RAGService
    ↓
DocumentChunk
    ↓
MilvusRepository
    ↓
Milvus
```

**上传知识库**

```
KnowledgeRouter
    ↓
KnowledgeService
    ↓
Document
    ↓
Chunk
    ↓
Embedding
    ↓
Milvus
```

---

## 二十八、现在先不要写 SQLAlchemy

这是非常重要的学习顺序。

我们现在处于：

```
阶段 1  需求
 ↓
阶段 2  领域模型
 ↓
阶段 3  业务流程
 ↓
阶段 4  ER 模型        ← 现在
 ↓
阶段 5  数据库表设计
 ↓
阶段 6  SQLAlchemy Model
 ↓
阶段 7  Repository
 ↓
阶段 8  Service
 ↓
阶段 9  Router
```

也就是说：

> SQLAlchemy 是"实现数据库模型"的工具，不是设计业务模型的起点。

---

## 二十九、我们目前第一版核心表

可以先定成下面这些：

| 模块 | 表 |
|------|-----|
| 租户 | tenant |
| 用户 | user |
| RBAC | role |
| RBAC | permission |
| RBAC | user_role |
| RBAC | role_permission |
| 会话 | conversation |
| 消息 | message |
| 工单 | ticket |
| 工单 | ticket_assignment |
| 订单 | order |
| 知识库 | knowledge_base |
| 文档 | document |
| 文档切片 | document_chunk |

> 第一版先不要疯狂增加表。
>
> 企业级不是"表越多越高级"，而是**业务边界清晰、关系合理、未来能够扩展**。

---

## 三十、最终形成我们的数据库全景

```
                         ┌──────────────┐
                         │    Tenant    │
                         └──────┬───────┘
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
             ▼                  ▼                  ▼
          User              KnowledgeBase        Role
             │                  │                  │
       ┌─────┼─────┐            ▼                  ▼
       │     │     │         Document          Permission
       │     │     │            │
       │     │     │            ▼
       │     │     │       DocumentChunk
       │     │     │            │
       │     │     │            ▼
       │     │     │          Milvus
       │     │     │
       │     │     └──────→ Order
       │     │
       │     ▼
       │ Conversation
       │     │
       │     ├──── Message
       │     │
       │     └──── Ticket
       │              │
       │              ▼
       │       TicketAssignment
       │
       ▼
    UserRole
       │
       ▼
      Role
```

---

## 三十一、这一阶段你真正需要掌握的不是"记表名"

而是学会一种**企业级数据库设计方法**：

```
看到业务流程
      ↓
找业务对象
      ↓
判断对象生命周期
      ↓
判断对象之间的关系
      ↓
1:1？
1:N？
N:M？
      ↓
设计中间表
      ↓
确定主键
      ↓
确定外键
      ↓
确定字段
      ↓
确定索引
      ↓
形成 ER 图
```

这套方法以后你做：

```
电商
CRM
ERP
AI Agent
客服系统
订单系统
流量池
```

都能复用。

---

## 三十二、第四阶段的下一步

现在 ER 模型已经出来了，但还不能直接写 SQLAlchemy。

**下一步应该做：**

> 《第五阶段：数据库表结构设计》

我们把刚才的：

```
Tenant
User
Role
Permission
Conversation
Message
Ticket
Order
KnowledgeBase
Document
DocumentChunk
```

逐张表真正设计出来。

每张表我们都会明确：

```
表名
 ↓
字段
 ↓
字段类型
 ↓
主键
 ↓
外键
 ↓
NULL / NOT NULL
 ↓
默认值
 ↓
唯一约束
 ↓
索引
 ↓
创建时间
 ↓
更新时间
 ↓
软删除
```

然后才进入真正的：

> 《第六阶段：SQLAlchemy ORM Model 设计》

届时你会看到：

```python
class User(Base):
    ...
```

为什么这么写、每一行对应数据库什么东西，以及：

```
Model
 ↓
Repository
 ↓
Service
 ↓
Router
```

到底是怎么真正连起来的。
