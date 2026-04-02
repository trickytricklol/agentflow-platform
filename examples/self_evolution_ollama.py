from agentflow.optimization import ModelTaskEvaluator, OptimizationExperiment, PromptCandidate, PromptOptimizer
from agentflow.providers import OpenAICompatibleProvider


def main():
    provider = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", "local-ollama")
    evaluator = ModelTaskEvaluator(provider, "计算 6 * 7，只输出最终数字", "42", model="qwen3:1.7b")
    experiment = OptimizationExperiment("准确回答并遵循输出格式", [
        PromptCandidate("请只输出数字42，不要任何其他内容。"),
        PromptCandidate("写一首关于春天的诗。"),
    ])
    best = PromptOptimizer(evaluator).run(experiment, rounds=2)
    print("history:", [(item.prompt, item.score) for item in experiment.history])
    print("best:", best.prompt, best.score)


if __name__ == "__main__":
    main()
