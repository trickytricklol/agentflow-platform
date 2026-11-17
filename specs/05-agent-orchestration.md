# 子规格 05：多 Agent 调度

## 目标

实现 Agent 能力注册、任务分发、并行调度、结果汇聚与失败隔离。

## 验收

- 复杂任务可拆成多个子任务并发执行。
- 单个子 Agent 失败不影响其他子任务结果。
- 所有调用可追踪，结果按任务 id 稳定排序。

## 实现

`AgentOrchestrator` 接收 `(agent_name, AgentTask)` 列表，使用线程池并行执行，返回按任务 id 排序的 `TaskResult`。`fail_fast=True` 时任一任务失败即取消剩余任务。

```python
orchestrator = AgentOrchestrator(max_workers=4)
orchestrator.register(AgentDefinition("researcher", "检索资料", handler))
results = orchestrator.execute([("researcher", AgentTask("t1", "检索", {"query": "q"}))])
```

## 扩展点

- 规划器：由上层 LLM 生成 `(agent_name, AgentTask)` 列表后交给调度器。
- 预算控制：在 `AgentDefinition` 外层增加调用配额与超时。
- 事件持久化：将 `TaskResult` 写入运行记录，供控制台展示。
