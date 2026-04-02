# 子规格 07：服务中台与持久化

实现 REST/SSE API、工作流 CRUD、版本发布、运行查询、模型/工具/Agent 注册、PostgreSQL 数据模型、Redis 任务队列和对象存储接口。

验收：API 文档可生成；租户和权限生效；运行事件可实时订阅；服务重启后可恢复必要状态。

当前实现提供内存版、JSON 持久化版和 SQLite 持久化版 `WorkflowRepository`、`WorkflowService` 与标准库 HTTP API：`GET /health`、`GET /workflows`、`GET /workflows/{id}`、`POST /workflows`、`POST /workflows/{id}/publish`、`POST /workflows/{id}/run`、`POST /workflows/{id}/run/stream`。运行流接口使用 SSE 返回节点事件。

已增加可选 `PostgresWorkflowRepository`；部署环境安装 `psycopg[binary]` 后，只需将 Repository 注入 `WorkflowService` 即可切换 PostgreSQL。
