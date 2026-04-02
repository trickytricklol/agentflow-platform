"""Acceptance checks mapped to the capabilities in the project description."""

from agentflow.agents import AgentDefinition, AgentOrchestrator, AgentTask
from agentflow.core import NodeResult, NodeStatus, WorkflowEngine, WorkflowGraph
from agentflow.nodes import AgentNode, LLMNode, ToolNode
from agentflow.optimization import OptimizationExperiment, PromptCandidate, PromptOptimizer
from agentflow.providers import MockProvider
from agentflow.tools import ToolDefinition, ToolRouter


def test_full_local_capability_chain():
    provider = MockProvider("local answer")
    router = ToolRouter()
    router.register(ToolDefinition("sum", "计算两个数字之和", lambda x, y: x + y, {"x": {}, "y": {}}))
    orchestrator = AgentOrchestrator(max_workers=2)
    orchestrator.register(AgentDefinition("worker", "执行专项任务", lambda task: task.input["value"] * 2))
    graph = WorkflowGraph.from_dsl({
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "llm", "type": "llm", "config": {"prompt": "hello {{input}}", "model": "local"}},
            {"id": "tool", "type": "tool", "config": {"tool": "sum", "args": {"x": 2, "y": 3}}},
            {"id": "agent", "type": "agent", "config": {"agent": "worker"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "llm"}, {"source": "llm", "target": "tool"},
            {"source": "tool", "target": "agent"}, {"source": "agent", "target": "end"},
        ],
    })
    result = WorkflowEngine(graph, {
        "start": lambda node, values: "started",
        "llm": LLMNode(provider),
        "tool": ToolNode({"sum": lambda x, y: x + y}),
        "agent": AgentNode({"worker": lambda values, config: values["tool"] * 2}),
        "end": lambda node, values: values["agent"],
    }).run({"input": "world"})
    assert result.status == NodeStatus.SUCCESS
    assert result.nodes["end"].value == 10
    assert len(provider.calls) == 1
    assert router.route("请计算两个数字")[0].tool.name == "sum"
    assert orchestrator.execute([("worker", AgentTask("t1", "double", {"value": 4}))])[0].value == 8


def test_prompt_optimization_loop_is_executable():
    experiment = OptimizationExperiment("准确率", [PromptCandidate("v1"), PromptCandidate("v2")])
    result = PromptOptimizer(lambda prompt: {"v1": 0.4, "v2": 0.9}[prompt]).run(experiment, 2)
    assert result.prompt == "v2"
    assert len(experiment.history) == 2


def test_retry_and_event_trace_are_available():
    graph = WorkflowGraph.from_dsl({"nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "tool"}], "edges": [{"source": "start", "target": "end"}]})
    attempts = {"count": 0}
    def flaky(node, values):
        attempts["count"] += 1
        return NodeResult(success=False, error="temporary") if attempts["count"] == 1 else "ok"
    result = WorkflowEngine(graph, {"start": lambda n, v: "start", "tool": flaky}, max_retries=1).run()
    assert result.status == NodeStatus.SUCCESS
    assert result.nodes["end"].attempts == 2
    assert any(event.status == NodeStatus.RUNNING for event in result.events)
