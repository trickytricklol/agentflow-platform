# 子规格 05：主从 Agent 调度

实现主 Agent 规划协议、手动子 Agent、自动拆解生成、能力注册、并行调度、结果汇聚、预算与最大深度控制。

验收：复杂任务可拆成多个子任务并发执行；子 Agent 失败可重试或降级；所有调用可追踪。

当前实现提供 `AgentOrchestrator`：主 Agent 或上层规划器生成 `(agent_name, AgentTask)` 列表后，调度器使用线程池并行执行并返回按任务 id 排序的 `TaskResult`。后续将接入 LLM 规划器、预算控制、重试和持久化事件。
