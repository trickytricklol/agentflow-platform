# 子规格 02：WorkflowEngine

在 DAG 核心上实现节点状态机、前后置关系、分支流转、失败处理、重试、超时、取消、事件记录和运行恢复。

第一版 Python API：`WorkflowEngine(graph, handlers, max_retries).run(context)`。处理器接收 `(node, values)`，可返回普通值或 `NodeResult(value, success, error)`。引擎输出 `RunResult`，包含节点状态、结果、错误、尝试次数和状态事件。

并行 API：`run_parallel(context, max_workers, timeout_seconds, cancel_event)`，按 DAG 拓扑层并发执行互不依赖的节点，再进入下一层汇聚；支持超时和取消；串行 `run()` 保留用于调试和确定性回放。

验收：五类节点可注册；状态转移合法；success/fail 分支可控；一次运行可查询完整事件链。
