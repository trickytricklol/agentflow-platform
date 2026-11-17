# 核心能力验收矩阵

| 能力 | 状态 | 自动化验证 |
|---|---|---|
| DAG 拓扑、循环检测、不可达检测 | 已实现 | `test_dag.py` |
| 节点状态、分支、重试、事件 | 已实现 | `test_engine.py`、`test_acceptance.py` |
| 开始 / LLM / 工具 / Agent / 结束节点 | 已实现 | `test_nodes.py`、`test_acceptance.py` |
| 多 Agent 并发调度 | 已实现 | `test_agents.py` |
| Tool Router 两阶段路由与参数校验 | 已实现 | `test_router.py` |
| OpenAI 兼容与 Ollama Provider | 已实现 | `test_provider.py` |
| JSON / SQLite 持久化 | 已实现 | `test_persistence.py`、`test_sqlite.py` |
| PostgreSQL 持久化 | 已实现（需 `psycopg`） | 可选依赖测试 |
| HTTP API、内置控制台与 SSE | 已实现 | 端到端运行校验 |
| 版本递增发布、历史与回滚 | 已实现 | `test_service.py`、`test_persistence.py` |
| 鉴权 / RBAC / 审计 / 指标 | 已实现 | `test_security.py` |
| 可视化画布 | 已实现 | 浏览器验收 |
| RBF GP / EI 有限预算选样 | 已实现 | `test_evolution.py` |
| 神经 Embedding 与词法 Embedding | 已实现 | `test_evolution.py` |
| 失败反思、候选变异、示例回放 | 已实现 | `test_evolution.py` |
| 单节点 / 字段分工 / 复核结构搜索 | 已实现 | `test_structural.py` |
| 验证门槛、冻结确认与回滚 | 已实现 | `test_structural.py`、`test_acceptance.py` |
| Pareto 合并与联合示例搜索 | 已实现 | `test_pareto.py`、`test_demonstrations.py` |
| 安全约束与切片门控 | 已实现 | `test_safe_bo.py` |
| 主从 Agent 调度 | 已实现 | `test_agents.py` |
| SSE 实时事件流 | 已实现 | 端到端运行校验 |
