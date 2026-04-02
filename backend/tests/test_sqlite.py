from agentflow.service import SqliteWorkflowRepository, WorkflowRecord


def test_sqlite_repository_survives_reload(tmpdir):
    path = str(tmpdir.join("agentflow.db"))
    repo = SqliteWorkflowRepository(path)
    repo.save(WorkflowRecord("w1", "sqlite", {"version": "1.0"}))
    restored = SqliteWorkflowRepository(path)
    assert restored.get("w1").name == "sqlite"
