# 架构设计

## 设计目标

AgentFlow 面向可私有化部署的 AI 工作流场景，围绕四个约束设计：

1. **可校验**：任何工作流在执行前必须通过结构化校验，非法图直接拒绝并给出定位信息。
2. **可观测**：节点状态、重试次数、错误、Token 用量与执行事件全程可追踪。
3. **可发布**：工作流以版本为单位发布，运行只使用已发布版本，任何优化结果都可回滚。
4. **可扩展**：模型、工具、Agent、存储均以接口或注册表形式接入，不把具体业务写进引擎。

## 分层结构

```text
┌─────────────────────────────────────────────────────────┐
│ Web 控制台（frontend/，由 API 在根路径托管）                  │
│ 画布 · 节点配置 · DSL 校验 · 保存/发布 · SSE 运行事件     │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────┐
│ API 层（backend/src/agentflow/api.py）                   │
│ 鉴权 · 审计 · 指标 · 工作流与模型路由                     │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ 服务层（service/workflow_service.py）                    │
│ 创建 · 校验 · 发布 · 运行 · 序列化                        │
└───────────────┬─────────────────────────┬───────────────┘
                │                         │
┌───────────────▼──────────────┐  ┌───────▼───────────────┐
│ Repository                   │  │ 执行引擎（core/）      │
│ Memory / JSON / SQLite /     │  │ DSL · DAG · 状态机     │
│ PostgreSQL                   │  │ 拓扑 · 并行 · 事件     │
└──────────────────────────────┘  └───────┬───────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
             ┌──────▼──────┐      ┌───────▼───────┐     ┌───────▼───────┐
             │ 模型适配层   │      │ 工具中心       │     │ Agent 协作     │
             │ Ollama      │      │ 路由 · 校验    │     │ 注册 · 调度    │
             │ OpenAI 兼容  │      │ 并行执行       │     │ 结果汇聚       │
             │ Mock        │      └───────────────┘     └───────────────┘
             └─────────────┘
```

## 工作流 DSL

```json
{
  "version": "1.0",
  "nodes": [
    {"id": "start", "type": "start", "config": {}},
    {"id": "classify", "type": "llm", "config": {"prompt": "判断工单类型：{{ticket}}", "model": "qwen3:1.7b"}},
    {"id": "route", "type": "tool", "config": {"tool": "assign_queue", "args": {"queue": "{{classify}}"}}},
    {"id": "end", "type": "end", "config": {}}
  ],
  "edges": [
    {"source": "start", "target": "classify", "when": "success"},
    {"source": "classify", "target": "route", "when": "success"},
    {"source": "route", "target": "end", "when": "success"}
  ]
}
```

### 节点类型

| 类型 | 作用 | 关键配置 |
|---|---|---|
| `start` | 唯一入口，注入运行上下文 | 无 |
| `llm` | 调用模型生成内容 | `prompt`、`model`、`temperature` |
| `tool` | 调用已注册工具 | `tool`、`args` |
| `agent` | 调用已注册 Agent | `agent` |
| `end` | 汇聚结果并结束 | 无 |

`llm` 节点的 `prompt` 支持 `{{变量}}` 插值，变量来自运行上下文与上游节点输出。`tool` 节点的 `args` 值写成 `{{变量}}` 时会替换为对应值，否则按字面量处理。

### 校验规则

| 规则 | 错误示例 |
|---|---|
| DSL 必须是对象 | `DSL must be an object` |
| 节点必须有 `id`，且全局唯一 | `duplicate node id: classify` |
| 节点必须有 `type` | `node type is required: node-3` |
| 边两端的节点必须存在 | `edge references unknown node: a->b` |
| 必须有且仅有一个 `start` 节点 | `workflow must contain exactly one start node, got 2` |
| 不允许循环依赖 | `cycle detected: a -> b -> a` |
| 所有节点必须从 `start` 可达 | `unreachable nodes: ['lonely']` |

校验失败抛出 `DagError`，API 返回 `400`，错误信息包含具体节点或边。

## 执行引擎

### 状态机

```text
INIT ──MARK──▶ MARK ──▶ RUNNING ──▶ SUCCESS
                              └──▶ ERROR
         │
         └──▶ SKIP（未满足分支条件）
```

- `MARK`：节点被调度，等待执行。
- `RUNNING`：本次尝试开始，`attempt` 从 1 递增。
- `SUCCESS`：结果写入运行上下文，后继节点可读取。
- `ERROR`：达到重试上限或处理器抛错；可按 `fail` 边进入兜底分支。
- `SKIP`：前置条件不满足，节点不执行。

### 分支激活

节点激活由入边条件决定：

| `when` | 激活条件 |
|---|---|
| `success` | 源节点状态为 `SUCCESS` |
| `fail` | 源节点状态为 `ERROR` |
| `always` / `*` | 源节点已结束，不论成功或失败 |

若没有任何入边条件成立，节点进入 `SKIP`。所有被选中的源节点结束后，节点才进入执行。

### 串行与并行

- `WorkflowEngine.run()` 按拓扑序串行执行，适合确定性流程与单元测试。
- `WorkflowEngine.run_parallel()` 按 DAG 层调度：同一层内无依赖的节点并发执行，层间通过 `values` 汇聚。
- 并行模式支持 `timeout_seconds` 与 `cancel_event`；超时节点标记为 `ERROR`，取消事件触发后未执行的节点标记为 `SKIP`。

### 事件

每次状态迁移生成 `EngineEvent(node_id, status, attempt, error)`。引擎支持 `on_event` 监听器，在 `MARK`、`RUNNING`、`SUCCESS`、`ERROR`、`SKIP` 发生时即时回调；API 的 `/run` 汇总完整事件列表，`/run/stream` 通过监听器实时写入 SSE，而不是等运行结束后回放。

## 服务层与存储

`WorkflowService` 负责工作流生命周期：

```text
create(name, dsl)   ──▶ 校验 ──▶ 持久化
update(id, name, dsl) ──▶ 重新校验 ──▶ 标记未发布
publish(id)         ──▶ 重新校验 ──▶ 版本 +1 ──▶ 追加发布历史
run(id, handlers)   ──▶ 必须已发布 ──▶ WorkflowEngine.run
rollback(id, ver)   ──▶ 恢复目标 DSL ──▶ 以新版本重新发布
```

| Repository | 适用场景 | 持久化方式 |
|---|---|---|
| `WorkflowRepository` | 单元测试、临时运行 | 进程内存 |
| `JsonWorkflowRepository` | 单机部署、本地开发 | JSON 文件 |
| `SqliteWorkflowRepository` | 单机持久化、免外部依赖 | SQLite 文件 |
| `PostgresWorkflowRepository` | 多实例部署 | PostgreSQL（需 `psycopg`） |

四套实现共享 `save / get / list` 契约，切换存储不影响服务层与 API。

## 治理

- **鉴权**：`AuthConfig` 支持 Bearer Token；关闭时返回开发主体 `Principal("development", {"admin"})`。
- **RBAC**：`authorize(principal, role)` 校验角色，`admin` 拥有全部权限。
- **审计**：`AuditLogger` 记录动作、主体、资源、详情与 UTC 时间戳，可追加写入 JSONL。
- **指标**：`Metrics` 维护计数器，`/health` 返回当前快照。

## 扩展点

| 扩展 | 方式 |
|---|---|
| 新模型服务 | 实现 `ModelProvider.chat()`，注册到 `ModelRegistry` |
| 新节点类型 | 在 `handlers` 中注册以 `(node, values)` 为签名的处理器 |
| 新工具 | `ToolRouter.register(ToolDefinition(...))` |
| 新 Agent | `AgentOrchestrator.register(AgentDefinition(...))` |
| 新存储 | 实现 `WorkflowRepository` 的 `save / get / list` |
| 新优化策略 | 在 `optimization/` 中实现采集函数或变异器，接入 `WorkflowEvaluator` |
