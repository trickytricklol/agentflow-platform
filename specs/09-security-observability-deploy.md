# 子规格 09：安全、可观测与部署

实现 OIDC/JWT、RBAC、审计、脱敏、限流、Prometheus 指标、OpenTelemetry 链路、结构化日志、Docker Compose 本地部署和 Kubernetes 生产模板。

验收：关键操作有审计；调用成本、延迟、错误率可观测；本地一键启动；敏感配置通过环境变量或密钥系统注入。

当前实现提供 `AuthConfig`/`Principal`/`authorize` 基础 RBAC、`AuditLogger` JSONL 审计记录、`Metrics` 计数器、Dockerfile 和 Docker Compose。生产环境应替换为 OIDC/JWT、Prometheus 和集中式日志系统。
