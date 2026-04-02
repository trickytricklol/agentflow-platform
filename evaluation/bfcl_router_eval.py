from __future__ import annotations

import json
from pathlib import Path

from agentflow.providers import OpenAICompatibleProvider
from agentflow.tools import ModelToolRouter, ToolDefinition, ToolRouter


DATA = Path("evaluation/external/BFCL/berkeley-function-call-leaderboard/bfcl_eval/data/BFCL_v4_simple_python.json")


def main(limit: int = 20):
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()[:limit]]
    router = ToolRouter()
    for row in rows:
        for function in row["function"]:
            router.register(ToolDefinition(function["name"], function["description"], lambda **kwargs: kwargs, function["parameters"]))
    model_router = ModelToolRouter(router, OpenAICompatibleProvider("http://127.0.0.1:11434/v1", "local-ollama"), "qwen3:1.7b")
    lexical_hits = 0
    model_hits = 0
    for row in rows:
        question = row["question"][0][0]["content"]
        expected = row["function"][0]["name"]
        routes = router.route(question, limit=1)
        model_route = model_router.route(question)
        lexical_hits += int(bool(routes and routes[0].tool.name == expected))
        model_hits += int(bool(model_route and model_route.tool.name == expected))
    print({"dataset": "BFCL_v4_simple_python", "samples": len(rows), "lexical_top1": lexical_hits / len(rows) if rows else 0.0, "model_top1": model_hits / len(rows) if rows else 0.0})


if __name__ == "__main__":
    main()
