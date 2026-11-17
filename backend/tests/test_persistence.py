from agentflow.service import JsonWorkflowRepository, WorkflowRecord


def test_json_repository_survives_reload(tmpdir):
    path = tmpdir.join("workflows.json")
    repo = JsonWorkflowRepository(path)
    record = WorkflowRecord("w1", "demo", {"nodes": [], "edges": []})
    repo.save(record)
    restored = JsonWorkflowRepository(path)
    assert restored.get("w1").name == "demo"


def test_json_repository_keeps_release_history(tmpdir):
    path = tmpdir.join("workflows.json")
    repo = JsonWorkflowRepository(path)
    record = WorkflowRecord("w1", "history", {"nodes": [], "edges": []}, version=2, published=True, history=[{"version": 1, "dsl": {"nodes": []}, "published_at": "now"}])
    repo.save(record)
    restored = JsonWorkflowRepository(path).get("w1")
    assert restored.version == 2
    assert restored.history[0]["version"] == 1


def test_json_repository_delete_survives_reload(tmpdir):
    path = tmpdir.join("workflows.json")
    repo = JsonWorkflowRepository(path)
    repo.save(WorkflowRecord("w1", "temporary", {"nodes": [], "edges": []}))
    assert repo.delete("w1") is True
    assert JsonWorkflowRepository(path).get("w1") is None
    assert repo.delete("w1") is False
