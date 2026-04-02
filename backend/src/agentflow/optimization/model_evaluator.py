from __future__ import annotations

from typing import Any, Callable
import re

from agentflow.providers import ChatMessage, ModelProvider


class ModelTaskEvaluator:
    """Turns a local/remote model into a PromptOptimizer evaluator."""

    def __init__(self, provider: ModelProvider, task: str, expected: str, *, model: str, score_fn: Callable[[str, str], float] | None = None):
        self.provider = provider
        self.task = task
        self.expected = expected
        self.model = model
        self.score_fn = score_fn or self.default_score

    def __call__(self, prompt: str) -> float:
        rendered = prompt.replace("{{task}}", self.task)
        response = self.provider.chat([ChatMessage("user", rendered)], model=self.model, temperature=0.0)
        return self.score_fn(response.content, self.expected)

    @staticmethod
    def default_score(output: str, expected: str) -> float:
        normalized_output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip().lower()
        normalized_expected = expected.strip().lower()
        if normalized_output == normalized_expected:
            return 1.0
        if normalized_expected in normalized_output:
            return 0.7
        return 0.0
