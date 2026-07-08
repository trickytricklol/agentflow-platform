# AgentFlow Platform 主规格说明

## 1. 目标与边界

构建一个支持可视化编排、DAG 执行、多模型接入、工具调用、主从 Agent 协作和 Prompt 自优化的企业级 AI 工作流平台。第一阶段优先完成可运行的单机 MVP，随后演进为可水平扩展的服务化系统。

非目标：第一阶段不实现模型训练、不绑定单一云厂商、不在核心引擎中硬编码具体业务流程。

## 2. 总体架构

1. 客户端：工作流画布、节点配置、运行监控、Prompt 优化面板。
2. 服务中台：工作流/版本/执行记录、模型与工具注册、鉴权、租户隔离。
3. 工作流引擎：DSL 校验、DAG 构建、状态机、分支、重试、超时、并行与事件流。
4. 工具中台：工具注册、Schema、权限、语义路由、渐进式 Prompt 加载。
5. 模型适配层：OpenAI、DeepSeek、通义千问及兼容 OpenAI 协议的模型。
6. Agent 协作层：主 Agent 规划、子 Agent 注册、调度、并行执行和结果汇聚。
7. 优化闭环：评估器、奖励函数、Embedding、Bayesian Optimization、版本对比与发布。

## 3. 核心领域模型

- Workflow：工作流基本信息、版本、状态、DSL、发布信息。
- Node：id、type、配置、输入输出 Schema、超时和重试策略。
- Edge：source、target、condition、分支类型。
- Run：一次执行的输入、状态、节点事件、输出、错误和成本。
- ModelProvider / ToolDefinition / AgentDefinition：可注册、可启停、可审计。
- OptimizationExperiment：目标、奖励函数、候选 Prompt、评估结果和当前最优版本。

## 4. DSL 约定

```json
{
  "version": "1.0",
  "nodes": [{"id": "start", "type": "start", "config": {}}],
  "edges": [{"source": "start", "target": "end", "when": "success"}]
}
```

节点类型：`start`、`llm`、`tool`、`agent`、`end`。分支边支持 `success`、`fail` 和表达式条件。DSL 必须拒绝重复节点、悬空边、多个开始节点、不可达节点和循环依赖。

## 5. 执行语义

- 先校验，再构建节点图，再执行。
- 节点状态：`INIT -> MARK -> RUNNING -> SUCCESS | ERROR | SKIP`。
- 一个节点所有必需前置节点成功后才能运行。
- 一对多支持并行分支；多对一支持结果汇聚。
- 失败按节点策略重试；超过次数进入 ERROR，并按 fail 边转移。
- 所有状态转移产生事件，支持日志、追踪和恢复。

## 6. 安全与治理

租户隔离、RBAC、密钥只存引用不落明文、工具白名单、沙箱执行、输入输出脱敏、审计日志、Prompt 注入防护、调用预算和限流。

## 7. 非功能指标

- DSL 校验结果可解释，错误包含节点/边定位。
- 核心执行引擎可单元测试，节点适配器可替换。
- 默认支持幂等执行、超时、重试和取消。
- MVP 先支持单机并发；服务化阶段支持队列、分布式锁和持久化恢复。

## 8. 交付阶段

见 `01-10` 子规格。每个子规格包含目标、接口、数据、验收标准和实现顺序；完成一个子规格后必须补充测试与运行说明。

当前算法优先级见 [10-workflow-self-evolution.md](10-workflow-self-evolution.md)：进化对象从节点指令扩展为受限 DAG 拓扑和训练经验。用真实执行反馈、预算内 GP/EI 搜索及独立验证发布证明闭环；规格中的企业级能力是目标，不能等同于全部已交付，实际状态以验收矩阵和实验报告为准。
