# 子规格 06：Prompt 与工作流优化

## 目标

实现奖励配置、评估数据集、候选生成、Embedding、Gaussian Process / Bayesian Optimization、版本比较与发布回滚。

## 验收

- 同一数据集上可比较多个候选。
- 每轮评估记录指标、Token 与延迟。
- 最优候选可发布，发布前保留回滚版本。

## 实现

- `OptimizationExperiment` / `PromptOptimizer`：候选评估与最优版本记录。
- `GaussianProcessOptimizer`：RBF 核、观测噪声、Expected Improvement 与多样性权重。
- `OllamaEmbeddingProvider` / `TfidfEmbedding`：神经向量与离线词法向量。
- `FeedbackMutator`：失败反思生成候选指令。
- `reward` 白名单：只接受 `exact_json` 指标与受限权重。

详细算法与运行方式见 [docs/optimization.md](../docs/optimization.md)。
