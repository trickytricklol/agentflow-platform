# 外部评估集

项目已通过 sparse clone 引入 Berkeley Function Calling Leaderboard（BFCL）数据源：

`evaluation/external/BFCL`

BFCL 覆盖简单、多函数、并行、多轮和 Agentic 工具调用场景。当前 MVP 取 `BFCL_v4_simple_python.json` 前 20 条做 Tool Router 验收：词法召回 Top-1 为 0.65，加入 Ollama 语义精排后 Top-1 为 0.70。

```powershell
cd D:\agent-workflow-platform
$env:PYTHONPATH="D:\agent-workflow-platform\backend\src"
python evaluation\bfcl_router_eval.py
```

来源：<https://github.com/EnlightenedAI/BFCL>。完整数据及评测协议以原仓库为准；项目本地只使用小切片做开发验证。
