# 《企业 AI 客服平台》第五阶段：数据库表结构设计（Table Design）V1.0

> 前文：PRD → 领域模型 → 核心业务流程 → 数据库 ER 模型 → 完整开发路线图 → 系统架构设计

> 注：本文 DDL 采用 MySQL 语法风格（AUTO_INCREMENT / DATETIME / LONGTEXT / TINYINT）。

## 本阶段要解决的问题

> 这是企业项目真正开始写代码前最重要的一步。

---

## 一、企业 AI 客服系统完整数据库

我先给你整个数据库全景：

```
用户体系
├── user
├── role
├── permission
├── user_role
└── role_permission

知识库体系
├── knowledge_base
├── document
├── document_chunk
└── vector_index

会话体系
├── conversation
├── message

AI体系
├── model_config
├── prompt_template

工单体系
├── ticket
├── ticket_message

日志体系
├── login_log
├── ai_call_log
├── operation_log

系统配置
├── tenant
├── api_key
└── system_config
```

- 真实企业项目：20~80 张表
- 你这个项目：**先设计 15 张核心表**

---

## 二、第一组：用户权限系统（RBAC）

### 1. user（用户表）

```sql
CREATE TABLE user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    username VARCHAR(50) UNIQUE,
    password_hash VARCHAR(255),

    nickname VARCHAR(50),

    email VARCHAR(100),

    phone VARCHAR(20),

    avatar VARCHAR(255),

    status TINYINT DEFAULT 1,

    tenant_id BIGINT,

    created_at DATETIME,
    updated_at DATETIME
);
```

**字段解释：**

| 字段 | 含义 |
|------|------|
| id | 用户ID |
| username | 登录账号 |
| password_hash | 加密密码 |
| tenant_id | 所属企业 |

例如：腾讯、阿里、字节都在同一个系统。

---

### 2. role（角色表）

```sql
CREATE TABLE role (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    name VARCHAR(50),

    code VARCHAR(50),

    description TEXT
);
```

例如：

```
admin
customer_service
knowledge_admin
employee
```

---

### 3. permission（权限表）

```sql
CREATE TABLE permission (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    name VARCHAR(100),

    code VARCHAR(100),

    api_path VARCHAR(255),

    method VARCHAR(10)
);
```

例如：

```
ticket:view
ticket:edit
kb:upload
user:delete
```

---

### 4. user_role

```sql
CREATE TABLE user_role (
    user_id BIGINT,
    role_id BIGINT
);
```

---

### 5. role_permission

```sql
CREATE TABLE role_permission (
    role_id BIGINT,
    permission_id BIGINT
);
```

---

## 三、知识库系统

这是 AI 客服的核心。

### 6. knowledge_base（知识库）

```sql
CREATE TABLE knowledge_base (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    tenant_id BIGINT,

    name VARCHAR(100),

    description TEXT,

    embedding_model VARCHAR(100),

    status TINYINT,

    created_by BIGINT,

    created_at DATETIME
);
```

例如：

```
产品知识库
售后知识库
合同知识库
FAQ知识库
```

---

### 7. document（文档）

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    kb_id BIGINT,

    file_name VARCHAR(255),

    file_size BIGINT,

    file_type VARCHAR(50),

    storage_path VARCHAR(500),

    status TINYINT,

    upload_user BIGINT,

    created_at DATETIME
);
```

状态：

```
0 上传中
1 解析中
2 切块中
3 向量化
4 完成
5 失败
```

---

### 8. document_chunk（切块表）

**这是最重要的表。**

```sql
CREATE TABLE document_chunk (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    document_id BIGINT,

    chunk_no INT,

    content TEXT,

    token_count INT,

    embedding_status TINYINT,

    created_at DATETIME
);
```

例子：

原文：

```
退货流程：
7天内可退货...
```

切成：

```
chunk1
chunk2
chunk3
```

---

### 9. vector_index（向量索引）

如果使用 Milvus / PGVector / ES Vector，可以保存映射关系：

```sql
CREATE TABLE vector_index (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    chunk_id BIGINT,

    vector_id VARCHAR(100),

    platform VARCHAR(50),

    created_at DATETIME
);
```

例如：

```
chunk_id = 123

Milvus:
vector_id = abc123
```

---

## 四、会话系统

### 10. conversation（会话表）

```sql
CREATE TABLE conversation (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    tenant_id BIGINT,

    user_id BIGINT,

    title VARCHAR(255),

    channel VARCHAR(50),

    status TINYINT,

    created_at DATETIME
);
```

渠道：

```
web
wechat
app
email
```

---

### 11. message（消息表）

**这是数据量最大的表。**

```sql
CREATE TABLE message (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    conversation_id BIGINT,

    sender_type VARCHAR(20),

    sender_id BIGINT,

    content LONGTEXT,

    message_type VARCHAR(20),

    token_count INT,

    created_at DATETIME
);
```

sender_type：

```
user
ai
human
system
```

---

## 五、AI 配置

### 12. model_config

```sql
CREATE TABLE model_config (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    model_name VARCHAR(100),

    provider VARCHAR(50),

    api_url VARCHAR(255),

    temperature DECIMAL(3,2),

    max_tokens INT
);
```

例如：

```
gpt-5
deepseek
qwen
claude
```

---

### 13. prompt_template

```sql
CREATE TABLE prompt_template (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    name VARCHAR(100),

    scene VARCHAR(50),

    content TEXT,

    version VARCHAR(20)
);
```

例如：

```
客服Prompt
销售Prompt
投诉Prompt
```

---

## 六、工单系统

AI 无法回答：

```
AI
↓
转人工
↓
工单
```

### 14. ticket

```sql
CREATE TABLE ticket (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    conversation_id BIGINT,

    user_id BIGINT,

    assigned_user BIGINT,

    status TINYINT,

    priority TINYINT,

    created_at DATETIME
);
```

状态：

```
待处理
处理中
已完成
关闭
```

---

### 15. ticket_message

```sql
CREATE TABLE ticket_message (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    ticket_id BIGINT,

    sender_id BIGINT,

    content TEXT,

    created_at DATETIME
);
```

---

## 七、数据库关系图

```
tenant
   │
   ├── user
   │      │
   │      ├── user_role
   │      │        │
   │      │        └── role
   │      │                 │
   │      │                 └── role_permission
   │      │                            │
   │      │                            └── permission
   │
   ├── knowledge_base
   │          │
   │          └── document
   │                     │
   │                     └── document_chunk
   │                                │
   │                                └── vector_index
   │
   ├── conversation
   │         │
   │         └── message
   │
   └── ticket
              │
              └── ticket_message
```

---

## 八、真实企业还会继续设计

下一步通常是：

> 第六阶段：索引设计

例如：

```
INDEX idx_user_tenant
INDEX idx_message_conversation
INDEX idx_chunk_document
INDEX idx_ticket_status
```

因为：

```
表设计完成
≠
数据库性能没问题
```

真正企业项目：

```
表结构
↓
索引
↓
分库分表
↓
缓存
↓
ES
↓
向量库
```
