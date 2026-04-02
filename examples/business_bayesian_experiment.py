from __future__ import annotations

import json
from pathlib import Path

from agentflow.optimization import GaussianProcessOptimizer, PromptMutator, TfidfEmbedding
from agentflow.providers import ChatMessage, OpenAICompatibleProvider


def score(output: str, expected: str) -> float:
    cleaned = output.lower().replace("<think>", "").replace("</think>", "")
    return 1.0 if expected.lower() in cleaned else 0.0


def main():
    cases = json.loads(Path("evaluation/business_eval.json").read_text(encoding="utf-8"))
    provider = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", "local-ollama")
    base = "请回答下面的企业任务：{{task}}"
    candidates = [base] + PromptMutator().mutate(base, "准确、简洁、严格遵守输出格式")
    corpus = candidates + [case["task"] for case in cases]
    embedding = TfidfEmbedding(corpus)

    def evaluate(prompt: str) -> float:
        scores = []
        for case in cases:
            request = prompt.replace("{{task}}", case["task"])
            response = provider.chat([ChatMessage("user", request)], model="qwen3:1.7b", temperature=0.0)
            scores.append(score(response.content, case["expected"]))
        return sum(scores) / len(scores)

    experiment = GaussianProcessOptimizer(embedding).run(candidates, evaluate, rounds=len(candidates))
    print("business_cases=", len(cases))
    print("observations=")
    for item in experiment.observations:
        print(round(item.score, 3), repr(item.prompt))
    best = max(experiment.observations, key=lambda item: item.score)
    print("best_score=", round(best.score, 3))
    print("best_prompt=", best.prompt)
    Path("evaluation/results/latest.json").write_text(json.dumps({
        "model": "qwen3:1.7b",
        "cases": len(cases),
        "candidate_count": len(candidates),
        "observations": [{"prompt": item.prompt, "score": item.score} for item in experiment.observations],
        "best_prompt": best.prompt,
        "best_score": best.score,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
