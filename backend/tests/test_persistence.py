from agentflow.service import JsonWorkflowRepository, WorkflowRecord


def test_json_repository_survives_reload(tmpdir):
    path = tmpdir.join("workflows.json")
    repo = JsonWorkflowRepository(path)
    record = WorkflowRecord("w1", "demo", {"nodes": [], "edges": []})
    repo.save(record)
    restored = JsonWorkflowRepository(path)
    assert restored.get("w1").name == "demo"
