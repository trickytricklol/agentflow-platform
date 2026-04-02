# 真实业务 Prompt 自进化实验

评估集位于 `evaluation/business_eval.json`，覆盖：

- 财务计算
- 客服工单分类
- 工具路由
- 关键字段抽取

运行：

```powershell
cd D:\agent-workflow-platform
$env:PYTHONPATH="D:\agent-workflow-platform\backend\src"
python examples\business_bayesian_experiment.py
```

实验流程：

1. 读取 8 条业务评估样本。
2. 对基础 Prompt 自动生成变异候选。
3. 使用 TF-IDF 向量作为离线 Embedding 基线。
4. 使用 Gaussian Process 和 Expected Improvement 选择实验顺序。
5. 让 Ollama 执行每条业务任务。
6. 依据期望标签计算准确率。
7. 输出各候选 Prompt 得分和最优版本。
