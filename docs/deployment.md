# 部署与运维

## 本地运行

```powershell
$env:PYTHONPATH="$PWD\backend\src"
python -m agentflow.api
```

```bash
PYTHONPATH=backend/src python -m agentflow.api
```

默认监听 `127.0.0.1:8080`，工作流数据写入当前目录的 `workflows.json`，审计日志写入 `audit.jsonl`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENTFLOW_HOST` | `127.0.0.1` | 监听地址；容器内可设为 `0.0.0.0` |
| `AGENTFLOW_PORT` | `8080` | 监听端口 |
| `AGENTFLOW_DATA_DIR` | `.` | 工作流与审计文件目录 |
| `AGENTFLOW_AUTH_ENABLED` | `0` | 设为 `1` 开启 Bearer Token 鉴权 |
| `AGENTFLOW_API_TOKEN` | `dev-token` | 鉴权 Token，生产环境必须替换 |
| `AGENTFLOW_OLLAMA_URL` | 空 | 设置后 API 使用原生 Ollama Provider 执行 `llm` 节点 |
| `AGENTFLOW_OPENAI_BASE_URL` | 空 | 设置后 API 使用 OpenAI 兼容 Provider |
| `AGENTFLOW_OPENAI_API_KEY` | 空 | OpenAI 兼容服务的 API Key |
| `AGENTFLOW_MODEL_TIMEOUT` | `120` | 模型请求超时（秒） |

Provider 选择顺序：`AGENTFLOW_OLLAMA_URL` → `AGENTFLOW_OPENAI_BASE_URL` → 内置 Mock Provider。

## Docker

```bash
docker build -t agentflow-api ./backend
docker run --rm -p 8080:8080 \
  -e AGENTFLOW_HOST=0.0.0.0 \
  -e AGENTFLOW_DATA_DIR=/app/data \
  -v agentflow-data:/app/data \
  agentflow-api
```

## Docker Compose

```bash
cd deploy
docker compose up --build
```

`deploy/docker-compose.yml` 暴露 `8080` 端口，并把命名卷 `agentflow-data` 挂载到 `/app/data`，工作流与审计日志随容器重建保留。

接入宿主机上的 Ollama 时，在 compose 中增加：

```yaml
environment:
  AGENTFLOW_OLLAMA_URL: "http://host.docker.internal:11434"
```

Linux 环境可将 `host.docker.internal` 替换为宿主机网桥地址，或让 Ollama 与 API 处于同一 Docker 网络。

## 鉴权

```bash
AGENTFLOW_AUTH_ENABLED=1 AGENTFLOW_API_TOKEN=change-me python -m agentflow.api
```

所有请求需携带 `Authorization: Bearer change-me`。Token 与主体、角色的映射在 `AuthConfig.tokens` 中维护，可按部署需要扩展为多 Token。

## 存储

| 场景 | Repository |
|---|---|
| 本地开发、临时运行 | `WorkflowRepository`（内存） |
| 单机持久化 | `JsonWorkflowRepository` 或 `SqliteWorkflowRepository` |
| 多实例 | `PostgresWorkflowRepository` |

PostgreSQL 适配需要额外安装：

```bash
pip install "psycopg[binary]"
```

```python
from agentflow.service import PostgresWorkflowRepository, WorkflowService

service = WorkflowService(PostgresWorkflowRepository("postgresql://user:pass@host:5432/agentflow"))
```

## 可观测性

- `GET /health` 返回服务状态与计数器快照。
- `audit.jsonl` 逐行记录 `workflow.create`、`workflow.publish`、`workflow.run` 等动作，包含主体、资源、详情与 UTC 时间戳。
- SSE 端点 `/workflows/{id}/run/stream` 输出 `event: node` 与 `event: complete`，可直接接入前端或日志采集。

## 反向代理

使用 Nginx 等反向代理时，需要为 SSE 关闭缓冲：

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

## 运行检查清单

1. `/health` 返回 `status: ok`。
2. 已注册至少一个可用模型，或配置了 `AGENTFLOW_OLLAMA_URL` / `AGENTFLOW_OPENAI_BASE_URL`。
3. 工作流保存前通过 DSL 校验，运行前已发布。
4. 生产环境已开启鉴权并替换默认 Token。
5. `AGENTFLOW_DATA_DIR` 指向持久化卷，备份策略覆盖 `workflows.json` 与 `audit.jsonl`。
