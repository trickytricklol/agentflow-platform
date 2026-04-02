from agentflow.providers import MockProvider
from agentflow.tools import ModelToolRouter, ToolDefinition, ToolRouter


def test_model_router_reranks_and_falls_back_safely():
    lexical = ToolRouter()
    lexical.register(ToolDefinition("weather", "查询天气", lambda: None))
    lexical.register(ToolDefinition("search", "搜索网页", lambda: None))
    reranked = ModelToolRouter(lexical, MockProvider('{"tool":"weather"}'), "mock").route("查询天气")
    assert reranked.tool.name == "weather"
    fallback = ModelToolRouter(lexical, MockProvider("not json"), "mock").route("查询天气")
    assert fallback.tool.name == "weather"
