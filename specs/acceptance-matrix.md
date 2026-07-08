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

## 自进化补充验收

| 能力 | 当前状态 | 验证 |
|---|---|---|
| RBF GP / EI 有限预算选样 | 已实现；效果不保证优于随机 | `test_evolution.py`、真实 Ollama 实验 |
| 神经 Embedding | nomic-embed-text 已本地运行 | 原始实验报告 |
| 训练失败反思、候选变异、示例回放 | 已实现；小模型可能产生低质量变异 | 候选谱系与失败实验 |
| 单节点/字段分工/复核结构进化 | 已实现受限模板搜索 | `test_structural.py`、结构实验 |
| 验证门槛与回滚 | 已实现 DSL 产物 | 单测；未接入生产版本库 |
| 主从自主规划 | 尚未实现 | 现有 Agent 测试只证明静态注册与调度 |
| SSE 实时执行流 | 尚未实现 | 当前为执行后事件回放 |

当前明确缺口：任意 DAG 自主生成、分布式队列/恢复、PostgreSQL 实例级测试、生产级 OIDC/JWT 和前端自动化测试。节点已有分层并行原型，但线程超时不能强杀阻塞插件。真实模型实验不代表 UI/API 所有节点均已接入真实适配器。
