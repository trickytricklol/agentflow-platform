from agentflow.core import NodeResult, NodeStatus, WorkflowEngine, WorkflowGraph


def make_graph(edges):
    return WorkflowGraph.from_dsl({"version": "1.0", "nodes": [
        {"id": "start", "type": "start"}, {"id": "work", "type": "tool"},
        {"id": "ok", "type": "end"}, {"id": "bad", "type": "end"}], "edges": edges})


def test_success_branch_skips_fail_branch():
    graph = make_graph([{"source": "start", "target": "work"}, {"source": "work", "target": "ok", "when": "success"}, {"source": "work", "target": "bad", "when": "fail"}])
    result = WorkflowEngine(graph, {"start": lambda n, v: "started", "tool": lambda n, v: "done", "end": lambda n, v: v.get("work")}).run()
    assert result.status == NodeStatus.SUCCESS
    assert result.nodes["ok"].status == NodeStatus.SUCCESS
    assert result.nodes["bad"].status == NodeStatus.SKIP


def test_retry_then_success():
    graph = make_graph([{"source": "start", "target": "work"}, {"source": "work", "target": "ok", "when": "success"}, {"source": "work", "target": "bad", "when": "fail"}])
    count = {"n": 0}
    def flaky(node, values):
        count["n"] += 1
        return NodeResult(success=False, error="temporary") if count["n"] == 1 else "recovered"
    result = WorkflowEngine(graph, {"start": lambda n, v: "started", "tool": flaky, "end": lambda n, v: "handled"}, max_retries=1).run()
    assert result.status == NodeStatus.SUCCESS
    assert result.nodes["work"].attempts == 2


def test_failure_routes_to_fail_branch():
    graph = make_graph([{"source": "start", "target": "work"}, {"source": "work", "target": "ok", "when": "success"}, {"source": "work", "target": "bad", "when": "fail"}])
    result = WorkflowEngine(graph, {"start": lambda n, v: "started", "tool": lambda n, v: NodeResult(success=False, error="broken"), "end": lambda n, v: "handled"}).run()
    assert result.status == NodeStatus.ERROR
    assert result.nodes["work"].status == NodeStatus.ERROR
    assert result.nodes["bad"].status == NodeStatus.SUCCESS
