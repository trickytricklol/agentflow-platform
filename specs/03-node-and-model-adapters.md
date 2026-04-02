# 子规格 03：节点与模型适配器

实现 LLM、Tool、Agent 节点协议，以及 OpenAI 兼容协议适配器；DeepSeek 和通义千问通过配置切换；统一流式输出、Token 用量、错误和重试模型。

验收：模型适配器可替换；密钥不进入日志；Mock provider 可完成离线测试。

当前实现提供 `ModelProvider`、`MockProvider`、`OpenAICompatibleProvider`、`LLMNode`、`ToolNode` 和 `AgentNode` 协议。生产 Provider 只需实现 `chat()`，不得把 API Key 写入节点配置或日志。

新增 `ModelRegistry` 与 `ModelConfig`，用于统一登记模型名称、Provider、模型版本和启用状态；API 提供 `GET/POST /models`。
