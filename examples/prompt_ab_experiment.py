from __future__ import annotations

import json
import re
import time
from pathlib import Path

from agentflow.providers import ChatMessage, OpenAICompatibleProvider


def normalize(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def evaluate(provider, cases, template):
    rows = []
    for case in cases:
        prompt = template.replace("{{task}}", case["task"])
        started = time.perf_counter()
        response = provider.chat([ChatMessage("user", prompt)], model="qwen3:1.7b", temperature=0.0)
        elapsed_ms = (time.perf_counter() - started) * 1000
        output = normalize(response.content)
        rows.append({"id": case["id"], "expected": case["expected"], "output": output, "correct": case["expected"].lower() in output.lower(), "exact": output.lower() == case["expected"].lower(), "latency_ms": elapsed_ms, "output_tokens": response.output_tokens})
    return rows


def summary(rows):
    return {"accuracy": sum(row["correct"] for row in rows) / len(rows), "exact_match": sum(row["exact"] for row in rows) / len(rows), "avg_latency_ms": sum(row["latency_ms"] for row in rows) / len(rows), "avg_output_tokens": sum(row["output_tokens"] for row in rows) / len(rows)}


def main():
    cases = json.loads(Path("evaluation/prompt_ab.json").read_text(encoding="utf-8"))
    provider = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", "local-ollama")
    baseline = evaluate(provider, cases, "请回答下面的任务：{{task}}")
    optimized = evaluate(provider, cases, "你是企业级 Agent 工作流节点。请准确完成任务。先理解任务，但最终只输出标准答案，不要解释、不要 Markdown、不要输出思考过程：{{task}}")
    result = {"model": "qwen3:1.7b", "samples": len(cases), "baseline": summary(baseline), "optimized": summary(optimized), "details": {"baseline": baseline, "optimized": optimized}}
    Path("evaluation/results").mkdir(parents=True, exist_ok=True)
    Path("evaluation/results/prompt_ab_latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("model", "samples", "baseline", "optimized")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
