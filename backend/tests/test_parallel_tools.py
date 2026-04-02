import time

from agentflow.tools import ToolDefinition, ToolRouter


def test_parallel_tool_execution_validates_and_aggregates():
    def slow(value):
        time.sleep(0.02)
        return value * 2
    tool = ToolDefinition("double", "double", slow, {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]})
    results = ToolRouter.execute_parallel([(tool, {"value": 2}), (tool, {"value": 3})], max_workers=2)
    assert [result.value for result in results] == [4, 6]
    assert all(result.success for result in results)


def test_parallel_tool_failure_is_isolated():
    tool = ToolDefinition("echo", "echo", lambda value: value, {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]})
    results = ToolRouter.execute_parallel([(tool, {"value": 1}), (tool, {"value": "ok"})])
    assert results[0].success is False
    assert results[1].success is True
