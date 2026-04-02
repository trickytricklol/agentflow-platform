from agentflow.optimization import ModelPromptMutator
from agentflow.providers import MockProvider


def test_model_prompt_mutator_parses_json_candidates():
    mutator = ModelPromptMutator(MockProvider('["variant a", "variant b"]'), "mock")
    assert mutator.mutate("base", "accuracy") == ["variant a", "variant b"]
