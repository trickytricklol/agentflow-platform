# Pareto 反思合并实验

协议：`hybrid case-objective Pareto parents; disagreement ASI; minibatch gate; full train then validation release`

Pareto 前沿：5 个候选；互补父代组合：10 个；实际合并：3 次。

| 合并 | 互补增益 | 拓扑 | mini-batch | 门控 | 完整训练 |
|---:|---:|---|---:|---|---:|
| 1 | 2.0 | review | 25.0% | True | 50.0% |
| 2 | 1.0 | direct | 50.0% | False | 未执行 |
| 3 | 1.0 | direct | 100.0% | True | 50.0% |

| 冻结版本 | 测试成功率 | Token |
|---|---:|---:|
| baseline | 62.5% | 6237 |
| best_merge_proposal | 50.0% | 14298 |
| released | 62.5% | 6237 |

发布：`False`；原因：validation did not improve。

mini-batch 只作低成本预筛。完整训练与独立验证仍决定是否发布；小批量改善不能作为最终收益。
