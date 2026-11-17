# 模型配置

AgentFlow 通过 `ModelProvider` 统一接入模型服务。每个 Provider 实现 `chat(messages, model=..., temperature=...)`，返回 `ModelResponse(content, model, input_tokens, output_tokens, raw)`。

## Ollama（原生接口）

```python
from agentflow.providers import OllamaProvider

provider = OllamaProvider("http://127.0.0.1:11434", timeout=120)
response = provider.chat(
    [ChatMessage("user", "把这条工单分类为账户、退款或故障")],
    model="qwen3:1.7b",
    temperature=0,
    seed=17,
    max_tokens=160,
)
```

原生接口调用 `/api/chat`，支持：

- `seed`：固定随机种子。
- `num_predict` / `max_tokens`：限制输出长度。
- `think=False`：关闭思考链，降低小模型延迟。

启动与拉取模型：

```bash
ollama serve
ollama pull qwen3:1.7b
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

## OpenAI 兼容接口

适用于 OpenAI、DeepSeek、通义千问及任意兼容 `/chat/completions` 的服务：

```python
from agentflow.providers import OpenAICompatibleProvider

provider = OpenAICompatibleProvider(
    base_url="https://api.example.com/v1",
    api_key="sk-...",
    timeout=60,
)
```

请求头自动带上 `Authorization: Bearer <api_key>`，Token 用量从响应的 `usage` 字段读取。

Ollama 也提供 OpenAI 兼容端点，可用于只支持 OpenAI 协议的客户端：

```python
provider = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", "ollama")
```

## Mock Provider

用于单元测试、离线联调与流程验证：

```python
from agentflow.providers import MockProvider

provider = MockProvider("固定回复")
```

`MockProvider` 会记录每次调用的消息列表，便于断言 Prompt 内容。

## 模型注册表

`ModelRegistry` 管理名称、Provider、模型标识与启用状态：

```python
from agentflow.providers import ModelConfig, ModelRegistry, OllamaProvider

registry = ModelRegistry()
registry.register(
    ModelConfig("local-qwen", "ollama", "qwen3:1.7b", "http://127.0.0.1:11434"),
    OllamaProvider("http://127.0.0.1:11434"),
)
config, provider = registry.get("local-qwen")
```

HTTP API 的 `POST /models` 使用同一注册表；节点通过 `config.model` 指定模型名。

## 嵌入模型

优化引擎需要文本向量。`optimization/embeddings.py` 提供两类实现：

| 实现 | 说明 |
|---|---|
| `TfidfEmbedding` | 纯标准库词法向量，无需外部服务 |
| `OllamaEmbedding` | 调用 Ollama `/api/embeddings`，默认 `nomic-embed-text` |

```python
from agentflow.optimization.embeddings import OllamaEmbedding

embedding = OllamaEmbedding("http://127.0.0.1:11434", "nomic-embed-text")
vector = embedding.embed("候选指令文本")
```

## 在节点中使用

```json
{
  "id": "classify",
  "type": "llm",
  "config": {
    "prompt": "根据以下工单判断路由与优先级：{{ticket}}",
    "model": "qwen3:1.7b",
    "temperature": 0
  }
}
```

`LLMNode` 会把 `config` 中的 `model` 与 `temperature` 透传给 Provider，并返回：

```json
{
  "content": "{\"route\": \"account\", \"priority\": \"P1\"}",
  "model": "qwen3:1.7b",
  "usage": {"input": 128, "output": 24}
}
```

## 超时与重试

- Provider 层 `timeout` 控制单次 HTTP 请求。
- 引擎层 `max_retries` 控制节点失败重试次数。
- 并行模式可设置 `timeout_seconds`，超时节点标记为 `ERROR` 并按 `fail` 边转移。

生产部署建议为模型服务配置独立超时、限流与重试预算，避免单个工作流耗尽连接池。
