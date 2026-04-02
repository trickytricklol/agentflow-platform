from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class ModelResponse:
    content: str
    model: str = "mock"
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class ModelProvider:
    """Provider contract. Concrete OpenAI-compatible clients can be plugged in later."""

    name = "base"

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.0, **kwargs: Any) -> ModelResponse:
        raise NotImplementedError


class MockProvider(ModelProvider):
    name = "mock"

    def __init__(self, response: str = "mock response"):
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages: list[ChatMessage], *, model: str = "mock", temperature: float = 0.0, **kwargs: Any) -> ModelResponse:
        self.calls.append(messages)
        return ModelResponse(self.response, model=model, input_tokens=sum(len(m.content) for m in messages), output_tokens=len(self.response))


class OpenAICompatibleProvider(ModelProvider):
    """Standard-library client for OpenAI-compatible chat endpoints."""

    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.0, **kwargs: Any) -> ModelResponse:
        payload = json.dumps({"model": model, "messages": [{"role": item.role, "content": item.content} for item in messages], "temperature": temperature, **kwargs}).encode("utf-8")
        request = Request(self.base_url + "/chat/completions", data=payload, headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
        choice = raw.get("choices", [{}])[0]
        usage = raw.get("usage", {})
        return ModelResponse(choice.get("message", {}).get("content", ""), raw.get("model", model), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), raw)
