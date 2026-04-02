import time

from agentflow.core import NodeStatus, WorkflowEngine, WorkflowGraph


def test_parallel_dag_layer_runs_concurrently():
    graph = WorkflowGraph.from_dsl({"nodes": [
        {"id": "start", "type": "start"}, {"id": "a", "type": "tool"},
        {"id": "b", "type": "tool"}, {"id": "end", "type": "end"}],
        "edges": [{"source": "start", "target": "a"}, {"source": "start", "target": "b"}, {"source": "a", "target": "end"}, {"source": "b", "target": "end"}]})
    def slow(node, values):
        time.sleep(0.05)
        return node.id
    started = time.perf_counter()
    result = WorkflowEngine(graph, {"start": lambda n, v: "ok", "tool": slow, "end": lambda n, v: [v["a"], v["b"]]}).run_parallel(max_workers=2)
    elapsed = time.perf_counter() - started
    assert result.status == NodeStatus.SUCCESS
    assert result.nodes["end"].value == ["a", "b"]
    assert elapsed < 0.09
