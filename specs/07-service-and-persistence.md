# 子规格 07：服务中台与持久化

实现 REST/SSE API、工作流 CRUD、版本发布与回滚、同步运行与流式运行、模型/工具/Agent 注册，以及内存、JSON、SQLite 与 PostgreSQL 四类 `WorkflowRepository`。

验收：API 文档与实现一致；Bearer Token 鉴权生效；运行事件可实时订阅；工作流与版本历史在服务重启后恢复；发布与回滚具备可审计记录。

当前实现提供 `WorkflowService` 与标准库 HTTP API：`GET /health`、`GET /ready`、`GET /metrics`、`GET /models`、`GET /workflows`、`GET /workflows/{id}`、`POST /workflows`、`PUT /workflows/{id}`、`DELETE /workflows/{id}`、`POST /workflows/{id}/publish`、`POST /workflows/{id}/rollback`、`POST /workflows/{id}/run`、`POST /workflows/{id}/run/stream`。运行流接口使用 SSE 返回节点事件，并发送心跳保持连接。

`PostgresWorkflowRepository` 为可选后端；部署环境安装 `psycopg[binary]` 后，将 Repository 注入 `WorkflowService` 即可切换 PostgreSQL。
