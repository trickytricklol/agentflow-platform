import threading
import time

from agentflow.core import NodeStatus, WorkflowEngine, WorkflowGraph


def make_graph():
    return WorkflowGraph.from_dsl({"nodes": [{"id": "start", "type": "start"}, {"id": "work", "type": "tool"}, {"id": "end", "type": "end"}], "edges": [{"source": "start", "target": "work"}, {"source": "work", "target": "end"}]})


def test_parallel_timeout_marks_node_error():
    def slow(node, values):
        time.sleep(0.05)
        return "done"
    result = WorkflowEngine(make_graph(), {"start": lambda n, v: "ok", "tool": slow, "end": lambda n, v: "end"}).run_parallel(timeout_seconds=0.01)
    assert result.status == NodeStatus.ERROR
    assert result.nodes["work"].error == "node execution timeout"


def test_parallel_cancel_skips_pending_nodes():
    cancelled = threading.Event()
    cancelled.set()
    result = WorkflowEngine(make_graph(), {"start": lambda n, v: "ok", "tool": lambda n, v: "done", "end": lambda n, v: "end"}).run_parallel(cancel_event=cancelled)
    assert result.nodes["start"].status == NodeStatus.SKIP
    assert result.nodes["end"].status == NodeStatus.SKIP


def test_sequential_cancel_stops_before_handlers_run():
    cancelled = threading.Event()
    cancelled.set()
    calls = []
    engine = WorkflowEngine(make_graph(), {
        "start": lambda n, v: calls.append("start"),
        "tool": lambda n, v: calls.append("tool"),
        "end": lambda n, v: calls.append("end"),
    })
    result = engine.run(cancel_event=cancelled)
    assert result.status == NodeStatus.ERROR
    assert calls == []
    assert result.nodes["start"].error == "run cancelled"
