# 《企业 AI 客服平台》第七阶段：接口 / API 设计 V1.0

> 前文：PRD → 领域模型 → 核心业务流程 → ER 模型 → 数据库表结构 → 系统架构

## 本阶段要解决的问题

这一阶段的目标是把前面的：PRD → 领域模型 → 业务流程 → ER 模型 → 数据库表 → 系统架构，真正转换成 **HTTP API**。

也就是说，从这一阶段开始，我们会开始回答：

> 前端到底调用什么接口？接口传什么？返回什么？谁能调用？调用之后系统做什么？

---

## 一、先确定 API 总体规范

我们的项目统一采用：

```
RESTful API
+
JSON
+
JWT
+
RBAC
+
SSE
```

**API 前缀：** `/api/v1`

例如：

```
POST /api/v1/auth/login
```

而不是：

```
POST /login
```

这样以后可以实现：

```
/api/v1
/api/v2
```

API 版本管理。

---

## 二、API 按业务模块划分

整个系统 API 分成：

```
/api/v1
│
├── /auth
│
├── /users
│
├── /roles
│
├── /conversations
│
├── /messages
│
├── /chat
│
├── /knowledge-bases
│
├── /documents
│
├── /tickets
│
├── /ai
│
└── /admin
```

---

## 三、第一组：认证 API

### 1. 用户登录

```
POST /api/v1/auth/login
```

**Request：**

```json
{
    "username": "zhangsan",
    "password": "123456"
}
```

**Response：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "access_token": "xxx",
        "token_type": "bearer",
        "expires_in": 3600
    }
}
```

**登录流程：**

```
用户
 ↓
POST /auth/login
 ↓
AuthRouter
 ↓
AuthService
 ↓
UserRepository
 ↓
PostgreSQL
 ↓
验证密码
 ↓
生成 JWT
 ↓
返回 Token
```

---

### 2. 获取当前用户

```
GET /api/v1/auth/me
```

**请求头：**

```
Authorization: Bearer <JWT>
```

**返回：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": 10001,
        "username": "zhangsan",
        "nickname": "张三",
        "roles": [
            "customer_service"
        ]
    }
}
```

---

## 四、用户 API

**获取用户：**

```
GET /api/v1/users/{user_id}
```

例如：

```
GET /api/v1/users/10001
```

**用户列表：**

```
GET /api/v1/users
```

支持：

```
?page=1
&page_size=20
&keyword=张三
&status=1
```

完整：

```
GET /api/v1/users?page=1&page_size=20&keyword=张三
```

**创建用户：**

```
POST /api/v1/users
```

```json
{
    "username": "lisi",
    "password": "123456",
    "nickname": "李四",
    "email": "lisi@example.com"
}
```

**修改用户：**

```
PUT /api/v1/users/{user_id}
```

**删除用户：**

```
DELETE /api/v1/users/{user_id}
```

---

## 五、会话 API

这是 AI 客服最核心的业务 API 之一。

**创建会话：**

```
POST /api/v1/conversations
```

**Request：**

```json
{
    "title": "退款问题"
}
```

**Response：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": 100001,
        "title": "退款问题",
        "status": "active"
    }
}
```

---

## 六、查询会话列表

```
GET /api/v1/conversations
```

例如：

```
GET /api/v1/conversations?page=1&page_size=20
```

**返回：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [
            {
                "id": 100001,
                "title": "退款问题",
                "status": "active",
                "created_at": "2026-09-09T10:00:00"
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 20
    }
}
```

---

## 七、查询会话消息

```
GET /api/v1/conversations/{conversation_id}/messages
```

例如：

```
GET /api/v1/conversations/100001/messages
```

**返回：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [
            {
                "id": 1,
                "sender_type": "user",
                "content": "退款多久到账？"
            },
            {
                "id": 2,
                "sender_type": "ai",
                "content": "退款通常会在3-5个工作日到账。"
            }
        ]
    }
}
```

---

## 八、最重要的 Chat API

这里要特别注意：

> **发送聊天消息 ≠ 普通 CRUD API。**

因为我们的 AI 要：Agent / RAG / LLM / Streaming。

所以：

```
POST /api/v1/chat
```

**Request：**

```json
{
    "conversation_id": 100001,
    "message": "退款多久到账？"
}
```

但是 AI 客服采用 **SSE**，所以不是简单返回 `{ "answer": "退款通常..." }`，而是：

```
data: {"type":"start"}

data: {"type":"content","content":"退款"}

data: {"type":"content","content":"通常"}

data: {"type":"content","content":"会在"}

data: {"type":"content","content":"3-5个工作日"}

data: {"type":"done"}
```

前端就可以实现"AI 正在回答..."，然后一个字一个字显示。

---

## 九、Chat API 的内部调用链

这是整个项目最值得掌握的一条链路：

```
POST /chat
      │
      ▼
ChatRouter
      │
      ▼
ChatService
      │
      ├── 保存 User Message
      │
      ▼
AIApplication
      │
      ▼
AI Router
      │
      ▼
Intent Recognition
      │
      ▼
Agent
      │
      ├──────────────┐
      ▼              ▼
     RAG          Business Tool
      │              │
      ▼              ▼
   Milvus          业务API
      │              │
      └──────┬───────┘
             ▼
            LLM
             │
             ▼
          SSE Stream
             │
             ▼
           Client
```

> 这条链路以后我们会真正写代码。

---

## 十、知识库 API

知识库也是一组完整 REST API。

**创建知识库：**

```
POST /api/v1/knowledge-bases
```

```json
{
    "name": "售后知识库",
    "description": "售后相关知识"
}
```

**获取知识库列表：**

```
GET /api/v1/knowledge-bases
```

**获取知识库详情：**

```
GET /api/v1/knowledge-bases/{kb_id}
```

**修改知识库：**

```
PUT /api/v1/knowledge-bases/{kb_id}
```

**删除知识库：**

```
DELETE /api/v1/knowledge-bases/{kb_id}
```

---

## 十一、文档 API

这里和知识库是：

```
Knowledge Base
      │
      └── Document
```

**上传文档：**

```
POST /api/v1/knowledge-bases/{kb_id}/documents
```

使用 **multipart/form-data**，而不是 JSON。

例如：

```
file = faq.pdf
```

---

## 十二、上传后的异步流程

接口不会一直等 PDF 处理完，而是：

```
POST /documents
       │
       ▼
保存文件
       │
       ▼
创建 Document
status = pending
       │
       ▼
发送 MQ Task
       │
       ▼
立即返回
```

**Response：**

```json
{
    "code": 0,
    "message": "document uploaded",
    "data": {
        "document_id": 20001,
        "status": "pending"
    }
}
```

后台：

```
Worker
 ↓
PDF Parser
 ↓
Chunk
 ↓
Embedding
 ↓
Milvus
 ↓
status = completed
```

---

## 十三、查询文档处理状态

```
GET /api/v1/documents/{document_id}
```

**返回：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": 20001,
        "file_name": "faq.pdf",
        "status": "completed",
        "chunk_count": 128
    }
}
```

这样前端就可以展示：

```
上传中
 ↓
解析中
 ↓
切块中
 ↓
向量化
 ↓
完成
```

---

## 十四、工单 API

AI 无法解决的问题：

```
AI
 ↓
转人工
 ↓
Ticket
```

**创建工单：**

```
POST /api/v1/tickets
```

```json
{
    "conversation_id": 100001,
    "title": "退款问题",
    "description": "用户要求人工处理退款",
    "priority": "high"
}
```

**工单列表：**

```
GET /api/v1/tickets
```

支持：

```
?page=1
&page_size=20
&status=pending
&priority=high
```

**工单详情：**

```
GET /api/v1/tickets/{ticket_id}
```

**分配工单：**

```
POST /api/v1/tickets/{ticket_id}/assign
```

```json
{
    "assignee_id": 10002
}
```

**更新工单状态：**

```
PATCH /api/v1/tickets/{ticket_id}/status
```

```json
{
    "status": "resolved"
}
```

---

## 十五、API 权限设计

API 不能只是"登录了就能访问"，而应该：

```
JWT
 ↓
User
 ↓
Role
 ↓
Permission
 ↓
API
```

例如：

**普通客服：**

```
conversation:view
conversation:create
ticket:view
ticket:create
```

**知识库管理员：**

```
knowledge:view
knowledge:create
knowledge:upload
knowledge:delete
```

**系统管理员：**

```
user:*
role:*
permission:*
```

---

## 十六、统一响应格式

我们统一：

```json
{
    "code": 0,
    "message": "success",
    "data": {}
}
```

**成功：**

```json
{
    "code": 0,
    "message": "success",
    "data": {}
}
```

**业务错误：**

```json
{
    "code": 40001,
    "message": "用户不存在",
    "data": null
}
```

**参数错误：**

```json
{
    "code": 42200,
    "message": "参数校验失败",
    "data": null
}
```

**未登录：**

```json
{
    "code": 40100,
    "message": "未登录",
    "data": null
}
```

**无权限：**

```json
{
    "code": 40300,
    "message": "无权限访问",
    "data": null
}
```

---

## 十七、HTTP Status Code 怎么用？

不要把所有错误都返回 200 OK，我们按照 HTTP 语义：

| 情况 | Status |
|------|--------|
| 查询成功 | 200 |
| 创建成功 | 201 |
| 删除成功 | 204 |
| 参数错误 | 422 |
| 未认证 | 401 |
| 无权限 | 403 |
| 资源不存在 | 404 |
| 冲突 | 409 |
| 服务异常 | 500 |

例如：

```
POST /users

创建成功：201 Created
用户不存在：404 Not Found
用户名重复：409 Conflict
```

---

## 十八、API 与数据库的关系

这里一定不要理解成：**一个 API = 一个数据库表**。

真实情况是：

```
API
 ↓
Service
 ↓
多个 Repository
 ↓
多个 Table
```

例如 `POST /api/v1/chat` 可能同时操作：

```
conversation
message
user
ai_call_log
```

所以：**API 是业务用例，不是数据库 CRUD 的简单包装。**

---

## 十九、最终 API 清单 V1

我们先确定第一版核心 API：

**认证：**

```
├── POST   /auth/login
└── GET    /auth/me
```

**用户：**

```
├── GET    /users
├── GET    /users/{id}
├── POST   /users
├── PUT    /users/{id}
└── DELETE /users/{id}
```

**会话：**

```
├── POST   /conversations
├── GET    /conversations
├── GET    /conversations/{id}
└── GET    /conversations/{id}/messages
```

**AI：**

```
└── POST   /chat
```

**知识库：**

```
├── POST   /knowledge-bases
├── GET    /knowledge-bases
├── GET    /knowledge-bases/{id}
├── PUT    /knowledge-bases/{id}
└── DELETE /knowledge-bases/{id}
```

**文档：**

```
├── POST   /knowledge-bases/{id}/documents
├── GET    /documents/{id}
└── DELETE /documents/{id}
```

**工单：**

```
├── POST   /tickets
├── GET    /tickets
├── GET    /tickets/{id}
├── POST   /tickets/{id}/assign
└── PATCH  /tickets/{id}/status
```

---

## 二十、最终形成 API 分层

现在把第七阶段和第六阶段连接起来：

```
                    HTTP Request
                         │
                         ▼
                ┌────────────────┐
                │     Router     │
                └───────┬────────┘
                        │
                 Request Schema
                        │
                        ▼
                ┌────────────────┐
                │    Service     │
                └───────┬────────┘
                        │
             ┌──────────┴──────────┐
             │                     │
             ▼                     ▼
         Domain                 AI
             │                     │
             │              ┌──────┴──────┐
             │              │             │
             │             RAG          Agent
             │              │             │
             │              ▼             ▼
             │           Milvus       Tools/API
             │                            │
             └──────────────┬─────────────┘
                            ▼
                       Repository
                            │
                            ▼
                       PostgreSQL
```

所以你现在应该能把整个项目串起来：

```
PRD
 ↓
业务流程
 ↓
领域模型
 ↓
数据库
 ↓
系统架构
 ↓
API
 ↓
代码实现
```

---

## 二十一、第七阶段的真正产物

这一阶段最后不是只得到一堆 URL。

我们最终要形成一份真正企业项目里的《API 接口规范》。

每一个 API 都固定描述：

```
① API 名称
② URL
③ HTTP Method
④ 是否需要 JWT
⑤ 所需 RBAC 权限
⑥ Path 参数
⑦ Query 参数
⑧ Body
⑨ Request Schema
⑩ Response Schema
⑪ HTTP Status
⑫ 错误码
⑬ Service 调用
⑭ 数据库操作
⑮ 是否异步
⑯ 是否 SSE
```

例如最终会把 `POST /api/v1/chat` 完整设计成：

```
Request
    ↓
ChatRequest
    ↓
JWT Authentication
    ↓
RBAC
    ↓
ChatRouter
    ↓
ChatService
    ↓
ConversationRepository
    ↓
MessageRepository
    ↓
AIApplication
    ↓
Agent
    ↓
RAG / Tool
    ↓
LLM
    ↓
SSE
    ↓
ChatResponse
```
