import pytest

from agentflow.core import DagError, DagExecutor, WorkflowGraph


def dsl(edges):
    return {
        "version": "1.0",
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "a", "type": "tool"},
            {"id": "b", "type": "tool"},
            {"id": "end", "type": "end"},
        ],
        "edges": edges,
    }


def test_topological_order_supports_fan_out_and_fan_in():
    graph = WorkflowGraph.from_dsl(dsl([
        {"source": "start", "target": "a"},
        {"source": "start", "target": "b"},
        {"source": "a", "target": "end"},
        {"source": "b", "target": "end"},
    ]))
    order = graph.topological_order()
    assert order[0] == "start"
    assert order[-1] == "end"
    assert order.index("a") < order.index("end")
    assert order.index("b") < order.index("end")


def test_cycle_is_rejected_with_path():
    with pytest.raises(DagError, match="cycle detected"):
        WorkflowGraph.from_dsl(dsl([
            {"source": "start", "target": "a"},
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
            {"source": "b", "target": "end"},
        ]))


def test_unreachable_node_is_rejected():
    with pytest.raises(DagError, match="unreachable"):
        WorkflowGraph.from_dsl(dsl([
            {"source": "start", "target": "a"},
            {"source": "a", "target": "end"},
        ]))


def test_executor_runs_dependencies_first():
    graph = WorkflowGraph.from_dsl(dsl([
        {"source": "start", "target": "a"},
        {"source": "a", "target": "end"},
        {"source": "start", "target": "b"},
        {"source": "b", "target": "end"},
    ]))
    result = DagExecutor(graph).run({
        "start": lambda node, values: "started",
        "tool": lambda node, values: f"{node.id}:{values['start']}",
        "end": lambda node, values: [values["a"], values["b"]],
    })
    assert result["end"] == ["a:started", "b:started"]
