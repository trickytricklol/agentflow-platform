from agentflow.optimization import OptimizationExperiment, PromptCandidate, PromptOptimizer


def test_prompt_optimizer_records_history_and_best():
    experiment = OptimizationExperiment("回答准确率", [PromptCandidate("bad"), PromptCandidate("good")])
    scores = {"bad": 0.2, "good": 0.9}
    best = PromptOptimizer(lambda prompt: scores[prompt]).run(experiment, rounds=2)
    assert best.prompt == "good"  # each candidate is evaluated once in round-robin baseline
    assert len(experiment.history) == 2
