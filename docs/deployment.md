# 部署与运维

## 本地运行

```powershell
$env:PYTHONPATH="$PWD\backend\src"
python -m agentflow.api
```

```bash
PYTHONPATH=backend/src python -m agentflow.api
```

默认监听 `127.0.0.1:8080`，工作流数据写入当前目录的 `workflows.json`，审计日志写入 `audit.jsonl`。浏览器访问 `http://127.0.0.1:8080` 使用内置控制台；开启鉴权后需在控制台填写 Token。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENTFLOW_HOST` | `127.0.0.1` | 监听地址；容器内可设为 `0.0.0.0` |
| `AGENTFLOW_PORT` | `8080` | 监听端口 |
| `AGENTFLOW_DATA_DIR` | `.` | 工作流与审计文件目录 |
| `AGENTFLOW_AUTH_ENABLED` | `0` | 设为 `1` 开启 Bearer Token 鉴权 |
| `AGENTFLOW_API_TOKEN` | 空 | 鉴权 Token；`AGENTFLOW_AUTH_ENABLED=1` 时必填，缺失则拒绝启动 |
| `AGENTFLOW_MAX_BODY_BYTES` | `1048576` | 单次请求体上限（字节），超限返回 `413` |
| `AGENTFLOW_CORS_ORIGINS` | `*` | 允许的跨域来源，逗号分隔；生产环境应改为控制台域名 |
| `AGENTFLOW_OLLAMA_URL` | 空 | 设置后 API 使用原生 Ollama Provider 执行 `llm` 节点 |
| `AGENTFLOW_OPENAI_BASE_URL` | 空 | 设置后 API 使用 OpenAI 兼容 Provider |
| `AGENTFLOW_OPENAI_API_KEY` | 空 | OpenAI 兼容服务的 API Key |
| `AGENTFLOW_MODEL_TIMEOUT` | `120` | 模型请求超时（秒） |

Provider 选择顺序：`AGENTFLOW_OLLAMA_URL` → `AGENTFLOW_OPENAI_BASE_URL` → 内置 Mock Provider。

## Docker

```bash
docker build -f backend/Dockerfile -t agentflow-api .
docker run --rm -p 8080:8080 \
  -e AGENTFLOW_HOST=0.0.0.0 \
  -e AGENTFLOW_DATA_DIR=/app/data \
  -v agentflow-data:/app/data \
  agentflow-api
```

构建上下文为仓库根目录，镜像同时包含后端与控制台；容器内 `AGENTFLOW_HOST` 默认已设为 `0.0.0.0`。CI 会在每次推送时构建镜像并启动服务，检查 `/health` 与根路径控制台。

## Docker Compose

```bash
cd deploy
cp .env.example .env
# 在 .env 中设置 AGENTFLOW_API_TOKEN 与 AGENTFLOW_CORS_ORIGINS
docker compose up --build
```

`deploy/docker-compose.yml` 暴露 `8080` 端口，并把命名卷 `agentflow-data` 挂载到 `/app/data`，工作流与审计日志随容器重建保留。Compose 默认开启鉴权并要求显式提供 Token；容器以非 root 用户运行，根文件系统只读，启用 `no-new-privileges`、`init` 与 `/health` 健康检查。

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

除 `/`、静态资源、`/health` 与 `/ready` 外的请求需携带 `Authorization: Bearer change-me`。开启鉴权但未提供 `AGENTFLOW_API_TOKEN` 时服务拒绝启动，不再使用固定默认 Token。Token 与主体、角色的映射在 `AuthConfig.tokens` 中维护，可按部署需要扩展为多 Token。

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

- `GET /health` 与 `GET /ready` 公开，分别用于存活与就绪探针；`GET /metrics` 受鉴权保护并返回计数器。
- `audit.jsonl` 逐行记录 `workflow.create`、`workflow.update`、`workflow.delete`、`workflow.publish`、`workflow.rollback`、`workflow.run` 等动作，包含主体、资源、详情与 UTC 时间戳。
- SSE 端点 `/workflows/{id}/run/stream` 在节点状态变化时实时输出 `event: node`，每 15 秒发送 `: ping` 心跳；客户端断开时取消后续节点。结束输出 `event: complete`，异常输出 `event: error`。

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

1. `/health` 返回 `status: ok`，根路径返回控制台页面。
2. 已注册至少一个可用模型，或配置了 `AGENTFLOW_OLLAMA_URL` / `AGENTFLOW_OPENAI_BASE_URL`。
3. 工作流保存前通过 DSL 校验，运行前已发布。
4. 生产环境已开启鉴权并显式设置强随机 `AGENTFLOW_API_TOKEN`，`AGENTFLOW_CORS_ORIGINS` 已收敛到实际域名。
5. `AGENTFLOW_DATA_DIR` 指向持久化卷，备份策略覆盖 `workflows.json` 与 `audit.jsonl`。
