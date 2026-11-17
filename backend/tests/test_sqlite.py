from agentflow.service import SqliteWorkflowRepository, WorkflowRecord


def test_sqlite_repository_survives_reload(tmpdir):
    path = str(tmpdir.join("agentflow.db"))
    repo = SqliteWorkflowRepository(path)
    repo.save(WorkflowRecord("w1", "sqlite", {"version": "1.0"}))
    restored = SqliteWorkflowRepository(path)
    assert restored.get("w1").name == "sqlite"


def test_sqlite_repository_keeps_release_history(tmpdir):
    path = str(tmpdir.join("agentflow.db"))
    repo = SqliteWorkflowRepository(path)
    repo.save(WorkflowRecord("w1", "history", {"nodes": []}, version=2, published=True, history=[{"version": 1, "dsl": {"nodes": []}, "published_at": "now"}]))
    restored = SqliteWorkflowRepository(path).get("w1")
    assert restored.version == 2
    assert restored.history[0]["version"] == 1


def test_sqlite_repository_delete_survives_reload(tmpdir):
    path = str(tmpdir.join("agentflow.db"))
    repo = SqliteWorkflowRepository(path)
    repo.save(WorkflowRecord("w1", "temporary", {"nodes": []}))
    assert repo.delete("w1") is True
    assert SqliteWorkflowRepository(path).get("w1") is None
    assert repo.delete("w1") is False
