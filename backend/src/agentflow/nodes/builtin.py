from __future__ import annotations

from typing import Any, Callable

from agentflow.providers import ChatMessage, ModelProvider


class LLMNode:
    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def __call__(self, node, values: dict[str, Any]) -> dict[str, Any]:
        prompt = str(node.config.get("prompt", ""))
        for key, value in values.items():
            prompt = prompt.replace("{{" + key + "}}", str(value))
        response = self.provider.chat([ChatMessage("user", prompt)], model=node.config.get("model", "default"), temperature=node.config.get("temperature", 0.0))
        return {"content": response.content, "model": response.model, "usage": {"input": response.input_tokens, "output": response.output_tokens}}


class ToolNode:
    def __init__(self, tools: dict[str, Callable[..., Any]]):
        self.tools = tools

    def __call__(self, node, values: dict[str, Any]) -> Any:
        name = node.config.get("tool")
        if name not in self.tools:
            raise ValueError(f"tool not registered: {name}")
        args = dict(node.config.get("args", {}))
        args = {key: (values.get(value[2:-2], value) if isinstance(value, str) and value.startswith("{{") and value.endswith("}}") else value) for key, value in args.items()}
        return self.tools[name](**args)


class AgentNode:
    def __init__(self, agents: dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]]):
        self.agents = agents

    def __call__(self, node, values: dict[str, Any]) -> Any:
        name = node.config.get("agent")
        if name not in self.agents:
            raise ValueError(f"agent not registered: {name}")
        return self.agents[name](values, node.config)
