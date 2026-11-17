# HTTP API

服务默认监听 `http://127.0.0.1:8080`，请求与响应均为 JSON（SSE 除外）。

## 鉴权

默认关闭鉴权。设置 `AGENTFLOW_AUTH_ENABLED=1` 后，所有请求必须携带：

```http
Authorization: Bearer <AGENTFLOW_API_TOKEN>
```

Token 缺失或无效返回 `401`：

```json
{"error": "Bearer token required"}
```

## 健康检查

```http
GET /health
```

```json
{
  "status": "ok",
  "metrics": {
    "workflow_runs": 12
  }
}
```

## 模型

### 列出模型

```http
GET /models
```

```json
[
  {"name": "mock-default", "provider": "mock", "model": "mock", "base_url": "", "enabled": true}
]
```

### 注册模型

```http
POST /models
Content-Type: application/json
```

```json
{
  "name": "local-qwen",
  "provider": "ollama",
  "model": "qwen3:1.7b",
  "base_url": "http://127.0.0.1:11434",
  "enabled": true
}
```

```json
{
  "name": "local-qwen",
  "provider": "ollama",
  "model": "qwen3:1.7b",
  "enabled": true
}
```

`provider` 支持 `ollama`、`openai-compatible` 与 `mock`。注册名 `name` 即节点 `config.model` 的取值；未注册的模型名回退到运行时默认 Provider（`AGENTFLOW_OLLAMA_URL` / `AGENTFLOW_OPENAI_BASE_URL` / Mock）。

## 工作流

### 创建工作流

```http
POST /workflows
Content-Type: application/json
```

```json
{
  "name": "工单分流",
  "dsl": {
    "version": "1.0",
    "nodes": [
      {"id": "start", "type": "start", "config": {}},
      {"id": "classify", "type": "llm", "config": {"prompt": "判断类型：{{ticket}}", "model": "qwen3:1.7b"}},
      {"id": "end", "type": "end", "config": {}}
    ],
    "edges": [
      {"source": "start", "target": "classify", "when": "success"},
      {"source": "classify", "target": "end", "when": "success"}
    ]
  }
}
```

保存前执行完整 DSL 校验，非法工作流返回 `400`。

```json
{
  "id": "7f6c2f5e-5b1a-4a0e-9a0e-2f6f9c8d1b3a",
  "name": "工单分流",
  "dsl": { "...": "..." },
  "version": 1,
  "published": false,
  "created_at": "2026-11-17T08:30:00+00:00"
}
```

### 工作流列表与详情

```http
GET /workflows
GET /workflows/{id}
```

列表返回工作流对象数组；详情返回单个对象。不存在时返回 `404`：

```json
{"error": "workflow not found"}
```

### 发布

```http
POST /workflows/{id}/publish
```

发布前重新校验 DSL，成功后 `published` 变为 `true`。未发布的工作流不能运行。

### 运行

```http
POST /workflows/{id}/run
Content-Type: application/json
```

```json
{
  "context": {
    "ticket": "无法登录，同时申请退款"
  }
}
```

```json
{
  "status": "SUCCESS",
  "nodes": {
    "start": {"status": "SUCCESS", "value": {"ticket": "无法登录，同时申请退款"}, "error": null},
    "classify": {"status": "SUCCESS", "value": {"content": "账户/退款"}, "error": null},
    "end": {"status": "SUCCESS", "value": {"ticket": "无法登录，同时申请退款", "start": {"ticket": "无法登录，同时申请退款"}, "answer": {"content": "账户/退款"}}, "error": null}
  },
  "events": [
    {"node_id": "start", "status": "MARK", "attempt": 0, "error": null},
    {"node_id": "start", "status": "RUNNING", "attempt": 1, "error": null},
    {"node_id": "start", "status": "SUCCESS", "attempt": 1, "error": null}
  ]
}
```

运行未发布的工作流返回 `400`：

```json
{"error": "workflow is not published"}
```

### SSE 运行事件流

```http
POST /workflows/{id}/run/stream
Content-Type: application/json
Accept: text/event-stream
```

```json
{"context": {"ticket": "无法登录"}}
```

响应为 `text/event-stream`，每个节点事件一帧，结束时发送 `complete`：

```text
event: node
data: {"node_id": "start", "status": "RUNNING", "attempt": 1, "error": null}

event: node
data: {"node_id": "start", "status": "SUCCESS", "attempt": 1, "error": null}

event: complete
data: {"status": "SUCCESS"}
```

## 错误码

| 状态码 | 场景 |
|---|---|
| `200` | 请求成功 |
| `201` | 创建工作流或注册模型成功 |
| `400` | DSL 校验失败、工作流未发布、JSON 解析失败、缺少字段 |
| `401` | 鉴权失败 |
| `404` | 路径或工作流不存在 |

错误响应统一为：

```json
{"error": "具体错误信息"}
```
