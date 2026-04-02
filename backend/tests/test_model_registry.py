from agentflow.providers import ModelConfig, ModelRegistry, MockProvider


def test_model_registry_hides_provider_secrets_and_lists_config():
    registry = ModelRegistry()
    registry.register(ModelConfig("demo", "mock", "v1"), MockProvider("ok"))
    assert registry.get("demo")[0].model == "v1"
    assert registry.list() == [{"name": "demo", "provider": "mock", "model": "v1", "base_url": "", "enabled": True}]
