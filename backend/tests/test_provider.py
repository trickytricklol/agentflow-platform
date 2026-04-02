from agentflow.providers import ChatMessage, MockProvider


def test_mock_provider_contract():
    result = MockProvider("ok").chat([ChatMessage("user", "hello")], model="demo")
    assert result.content == "ok"
    assert result.model == "demo"
