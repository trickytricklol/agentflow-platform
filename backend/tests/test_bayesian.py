from agentflow.optimization import BayesianExperiment, GaussianProcessOptimizer, PromptMutator, TfidfEmbedding


def test_tfidf_embedding_and_gp_select_best_candidate():
    candidates = ["answer accurately", "write poetry", "return exact answer"]
    embedding = TfidfEmbedding(candidates)
    experiment = GaussianProcessOptimizer(embedding).run(candidates, lambda prompt: {"answer accurately": 0.6, "write poetry": 0.1, "return exact answer": 0.95}[prompt], rounds=3)
    assert max(experiment.observations, key=lambda item: item.score).prompt == "return exact answer"
    assert len(embedding.embed("answer accurately")) == len(embedding.embed("write poetry"))


def test_prompt_mutation_generates_multiple_variants():
    variants = PromptMutator().mutate("Answer the task", "accuracy")
    assert len(variants) == 5
    assert any("只输出最终答案" in variant for variant in variants)
