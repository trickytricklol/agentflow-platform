from concurrent.futures import ThreadPoolExecutor

from agentflow.service import JsonWorkflowRepository, SqliteWorkflowRepository, WorkflowRecord


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


def _write_many(repository, count):
    def save(index):
        return repository.save(WorkflowRecord(f"w{index}", f"job-{index}", {"nodes": [], "edges": []}))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save, range(count)))


def test_json_repository_handles_concurrent_writes(tmpdir):
    path = tmpdir.join("workflows.json")
    repository = JsonWorkflowRepository(path)
    _write_many(repository, 24)
    assert len(repository.list()) == 24
    assert len(JsonWorkflowRepository(path).list()) == 24


def test_sqlite_repository_handles_concurrent_writes(tmpdir):
    path = str(tmpdir.join("agentflow.db"))
    repository = SqliteWorkflowRepository(path)
    _write_many(repository, 24)
    assert len(repository.list()) == 24
    assert len(SqliteWorkflowRepository(path).list()) == 24
