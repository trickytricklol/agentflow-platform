# 核心能力验收矩阵

| 能力 | 当前状态 | 自动化验证 |
|---|---|---|
| DAG 拓扑、循环检测、不可达检测 | 已通过 | `test_dag.py` |
| 节点状态、分支、重试、事件 | 已通过 | `test_engine.py`、`test_acceptance.py` |
| 开始/LLM/工具/Agent/结束节点 | 已通过 Mock | `test_nodes.py`、`test_acceptance.py` |
| 主从 Agent 并发调度 | 已通过 | `test_agents.py` |
| Tool Router 两阶段加载 | 已通过 | `test_router.py` |
| Prompt 优化闭环基线 | 已通过 | `test_prompt.py` |
| OpenAI 兼容 Provider | 已通过 Mock/本地 Ollama | `test_provider.py`、手工集成测试 |
| JSON/SQLite 持久化 | 已通过 | `test_persistence.py`、`test_sqlite.py` |
| PostgreSQL | 代码已提供，需真实数据库 | 可选依赖测试 |
| HTTP API / SSE | 代码已提供，需启动服务验收 | 手工/待补充端到端测试 |
| 鉴权/RBAC/审计/指标 | 已通过基础测试 | `test_security.py` |
| 前端画布 | MVP 已完成 | 浏览器验收 |

当前明确缺口：真正的高斯过程 Bayesian Optimization、工作流节点级并行、分布式队列/恢复、PostgreSQL 实例级测试、生产级 OIDC/JWT 和前端自动化测试。
