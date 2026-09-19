# Pareto 反思合并实验

协议：`instance Pareto parents; disagreement ASI; minibatch gate; full train then validation release`

Pareto 前沿：1 个候选；互补父代组合：0 个；实际合并：0 次。

| 合并 | 互补增益 | 拓扑 | mini-batch | 门控 | 完整训练 |
|---:|---:|---|---:|---|---:|

| 冻结版本 | 测试成功率 | Token |
|---|---:|---:|
| baseline | 70.8% | 6237 |
| best_merge_proposal | 70.8% | 6237 |
| released | 70.8% | 6237 |

发布：`False`；原因：validation did not improve。

mini-batch 只作低成本预筛。完整训练与独立验证仍决定是否发布；小批量改善不能作为最终收益。
