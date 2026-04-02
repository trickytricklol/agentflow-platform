from agentflow.optimization import ModelTaskEvaluator
from agentflow.providers import MockProvider


def test_model_task_evaluator_is_compatible_with_optimizer():
    evaluator = ModelTaskEvaluator(MockProvider("42"), "1+1", "42", model="mock")
    assert evaluator("请只回答 {{task}} 的结果") == 1.0
