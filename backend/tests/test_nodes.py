from agentflow.nodes import AgentNode, LLMNode, ToolNode
from agentflow.providers import MockProvider


class Node:
    def __init__(self, config):
        self.config = config


def test_llm_node_uses_template_and_returns_usage():
    provider = MockProvider("hello")
    result = LLMNode(provider)(Node({"prompt": "say {{name}}", "model": "test"}), {"name": "world"})
    assert result["content"] == "hello"
    assert provider.calls[0][0].content == "say world"
    assert result["usage"]["output"] == 5


def test_tool_and_agent_nodes_dispatch_registered_capabilities():
    tool_result = ToolNode({"add": lambda x, y: x + y})(Node({"tool": "add", "args": {"x": 2, "y": "{{n}}"}}), {"n": 3})
    agent_result = AgentNode({"worker": lambda values, config: values["task"]})(Node({"agent": "worker"}), {"task": "done"})
    assert tool_result == 5
    assert agent_result == "done"
