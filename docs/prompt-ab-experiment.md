# Prompt A/B 对比实验

实验脚本：`examples/prompt_ab_experiment.py`

对比：

- Baseline：简单回答任务
- Optimized：企业 Agent 角色、任务约束、严格输出格式

指标：准确率、Exact Match、平均延迟、平均输出 Token。

运行：

```powershell
cd D:\agent-workflow-platform
$env:PYTHONPATH="D:\agent-workflow-platform\backend\src"
python examples\prompt_ab_experiment.py
```
