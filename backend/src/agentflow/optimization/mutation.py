from __future__ import annotations

from typing import Any
import json

from agentflow.providers import ChatMessage, ModelProvider


class PromptMutator:
    """Automatic prompt mutation strategy with deterministic offline fallback."""

    def mutate(self, prompt: str, objective: str) -> list[str]:
        return [
            prompt + "\n请只输出最终答案，不要解释。",
            prompt + "\n请先检查答案，再按要求输出。",
            "你是严谨的企业 Agent。" + prompt,
            prompt + f"\n优化目标：{objective}。",
            prompt + "\n严格遵守任务中给出的候选集合，只输出一个标准答案，不要 Markdown、不要推理过程。",
        ]


class ModelPromptMutator(PromptMutator):
    def __init__(self, provider: ModelProvider, model: str):
        self.provider = provider
        self.model = model

    def mutate(self, prompt: str, objective: str) -> list[str]:
        request = f"请针对以下 Prompt 生成 4 个改进候选，只返回 JSON 字符串数组。目标：{objective}\n原 Prompt：{prompt}"
        try:
            response = self.provider.chat([ChatMessage("user", request)], model=self.model, temperature=0.7).content
            cleaned = response[response.find("["):response.rfind("]") + 1]
            variants = json.loads(cleaned)
            if isinstance(variants, list) and all(isinstance(item, str) and item.strip() for item in variants):
                return variants[:4]
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        return super().mutate(prompt, objective)
