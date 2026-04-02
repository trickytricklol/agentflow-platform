from agentflow.tools import ToolDefinition, ToolRouter


def test_router_manifest_is_lightweight_and_auto_route_loads_selected_schema():
    router = ToolRouter()
    router.register(ToolDefinition("weather", "查询天气预报", lambda city: city, {"city": {"type": "string"}}, tags={"天气"}))
    router.register(ToolDefinition("search", "搜索网页内容", lambda q: q, {"q": {"type": "string"}}, tags={"搜索"}))
    assert "parameters" not in router.manifest()[0]
    routes = router.route("请查询天气", mode="auto")
    assert routes[0].tool.name == "weather"
    assert ToolRouter.load_schemas(routes)[0]["parameters"]["city"]["type"] == "string"


def test_manual_route_and_disabled_tool():
    router = ToolRouter()
    router.register(ToolDefinition("a", "工具 A", lambda: 1, enabled=False))
    try:
        router.route("a", mode="manual", tool_name="a")
        assert False, "disabled tool should not be routable"
    except ValueError:
        pass
