from __future__ import annotations

from dataclasses import dataclass, field
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
import json

from agentflow.providers import ChatMessage, ModelProvider


@dataclass
class ToolDefinition:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    tags: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ToolRoute:
    tool: ToolDefinition
    score: float
    reason: str


class ToolValidationError(ValueError):
    pass


@dataclass
class ToolExecutionResult:
    tool: str
    success: bool
    value: Any = None
    error: str | None = None


class ToolRouter:
    """Two-stage router: cheap manifest selection, then full schema loading."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name or not tool.description:
            raise ValueError("tool name and description are required")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def manifest(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "tags": sorted(t.tags)} for t in self._tools.values() if t.enabled]

    def route(self, query: str, *, mode: str = "auto", tool_name: str | None = None, limit: int = 3) -> list[ToolRoute]:
        enabled = [tool for tool in self._tools.values() if tool.enabled]
        if mode == "manual":
            selected = next((tool for tool in enabled if tool.name == tool_name), None)
            if selected is None:
                raise ValueError(f"tool not available: {tool_name}")
            return [ToolRoute(selected, 1.0, "manual selection")]
        if mode != "auto":
            raise ValueError("mode must be auto or manual")
        query_words = self._words(query)
        ranked = []
        for tool in enabled:
            name_words = self._words(tool.name)
            corpus = self._words(" ".join([tool.description, " ".join(tool.tags)]))
            name_overlap = {query_word for query_word in query_words for corpus_word in name_words if query_word in corpus_word or corpus_word in query_word}
            overlap = {query_word for query_word in query_words for corpus_word in corpus if query_word in corpus_word or corpus_word in query_word}
            score = (3 * len(name_overlap) + len(overlap)) / max(1, len(query_words))
            if score > 0:
                matched = sorted(name_overlap | overlap)
                ranked.append(ToolRoute(tool, score, f"matched terms: {', '.join(matched)}"))
        return sorted(ranked, key=lambda route: route.score, reverse=True)[:limit]

    @staticmethod
    def _words(text: str) -> set[str]:
        stopwords = {"calculate", "find", "given", "what", "are", "the", "of", "a", "an", "to", "for", "with", "from", "and", "all", "where", "using", "function", "number", "value", "values"}
        words = {word.lower() for word in re.findall(r"[a-zA-Z0-9_]+", text) if len(word) > 1 and word.lower() not in stopwords}
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        words.update(chinese[index:index + 2] for index in range(len(chinese) - 1))
        return words

    @staticmethod
    def load_schemas(routes: list[ToolRoute]) -> list[dict[str, Any]]:
        return [{"name": route.tool.name, "description": route.tool.description, "parameters": route.tool.schema} for route in routes]

    @staticmethod
    def validate_arguments(tool: ToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
        schema = tool.schema or {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            raise ToolValidationError(f"missing required arguments: {', '.join(missing)}")
        unknown = set(arguments) - set(properties)
        if unknown:
            raise ToolValidationError(f"unknown arguments: {', '.join(sorted(unknown))}")
        for name, value in arguments.items():
            expected = properties.get(name, {}).get("type")
            valid = expected in (None, "any") or (expected == "string" and isinstance(value, str)) or (expected == "integer" and isinstance(value, int) and not isinstance(value, bool)) or (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or (expected == "boolean" and isinstance(value, bool)) or (expected == "array" and isinstance(value, list)) or (expected == "object" and isinstance(value, dict))
            if not valid:
                raise ToolValidationError(f"invalid type for {name}: expected {expected}")
        return arguments

    @staticmethod
    def execute_parallel(calls: list[tuple[ToolDefinition, dict[str, Any]]], max_workers: int = 4) -> list[ToolExecutionResult]:
        def execute(call: tuple[ToolDefinition, dict[str, Any]]) -> ToolExecutionResult:
            tool, arguments = call
            try:
                ToolRouter.validate_arguments(tool, arguments)
                return ToolExecutionResult(tool.name, True, tool.handler(**arguments))
            except Exception as exc:
                return ToolExecutionResult(tool.name, False, error=str(exc))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(execute, call) for call in calls]
            return [future.result() for future in futures]


class ModelToolRouter:
    """Semantic reranker over lexical candidates, with safe lexical fallback."""

    def __init__(self, router: ToolRouter, provider: ModelProvider, model: str):
        self.router = router
        self.provider = provider
        self.model = model

    def route(self, query: str, *, limit: int = 5) -> ToolRoute | None:
        candidates = self.router.route(query, limit=limit)
        if not candidates:
            return None
        manifest = [{"name": item.tool.name, "description": item.tool.description, "parameters": item.tool.schema} for item in candidates]
        prompt = "你是工具路由器。根据用户请求从候选工具中选一个，只返回 JSON：{\"tool\":\"工具名\"}。候选工具：" + json.dumps(manifest, ensure_ascii=False) + "\n用户请求：" + query
        try:
            content = self.provider.chat([ChatMessage("user", prompt)], model=self.model, temperature=0.0).content
            start, end = content.find("{"), content.rfind("}")
            parsed = json.loads(content[start:end + 1])
            selected = next((item for item in candidates if item.tool.name == parsed.get("tool")), None)
            if selected:
                return ToolRoute(selected.tool, min(1.0, selected.score + 0.01), "model rerank")
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        return candidates[0]
