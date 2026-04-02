# Prompt 自进化 MVP 验证

## 闭环

```text
候选 Prompt
  -> Ollama 执行任务
  -> 评估器计算分数
  -> 记录实验历史
  -> 选择当前最优 Prompt
```

运行：

```powershell
cd D:\agent-workflow-platform
$env:PYTHONPATH="D:\agent-workflow-platform\backend\src"
python examples\self_evolution_ollama.py
```

当前已用 `qwen3:1.7b` 验证：严格回答候选得分 1.0，无关候选得分 0.0，优化器能够选出最优候选。

生产增强方向：接入真实评估数据集、业务奖励函数、Embedding 向量、Gaussian Process Bayesian Optimization、候选 Prompt 自动变异、实验成本约束和版本发布/回滚。
