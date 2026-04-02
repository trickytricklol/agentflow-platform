# 子规格 06：Prompt 贝叶斯自适应优化

实现自然语言目标解析、奖励函数配置、评估数据集、Prompt Embedding、Gaussian Process/Bayesian Optimization、候选版本、实验停止条件和发布回滚。

验收：给定同一数据集可比较候选 Prompt；每轮实验有指标和成本；最优版本可发布与回滚。MVP 允许使用可替换的 Embedding/优化器接口。

当前实现提供 `PromptOptimizer` 与 `OptimizationExperiment`。评估器通过函数注入，优化器记录每轮分数和当前最优版本；后续将把候选生成、Embedding 和 Gaussian Process 策略替换为正式实现。
