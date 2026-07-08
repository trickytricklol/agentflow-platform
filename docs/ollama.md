# 本地 Ollama 推理

当前机器已经验证可用：

- 地址：`http://127.0.0.1:11434`
- 模型：`qwen3:1.7b`（当前 MVP 默认验证模型）
- 变异模型：`qwen3:4b`（已完成下载并用于结构搜索实验）
- Embedding：`nomic-embed-text`（本地 768 维向量）
- OpenAI 兼容地址：`http://127.0.0.1:11434/v1`

启动/查看模型：

```powershell
ollama list
ollama run qwen3:4b
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
