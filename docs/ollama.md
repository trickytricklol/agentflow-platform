# 本地 Ollama 推理

当前机器已经验证可用：

- 地址：`http://127.0.0.1:11434`
- 模型：`qwen3:1.7b`（当前 MVP 默认验证模型）
- OpenAI 兼容地址：`http://127.0.0.1:11434/v1`

启动/查看模型：

```powershell
ollama list
ollama run qwen3:0.6b
```

AgentFlow Provider 配置：

```python
from agentflow.providers import OpenAICompatibleProvider

provider = OpenAICompatibleProvider(
    "http://127.0.0.1:11434/v1",
    "local-ollama",
)
```

已验证 `start -> llm -> end` 工作流可以成功执行；`ModelTaskEvaluator` 可将模型调用接入 PromptOptimizer，形成“候选 Prompt → 任务执行 → 评分 → 选择最优”的自进化闭环。
