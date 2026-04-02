import pytest

from agentflow.service import WorkflowService


DSL = {"nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}], "edges": [{"source": "start", "target": "end"}]}


def test_create_publish_and_run_workflow():
    service = WorkflowService()
    record = service.create("demo", DSL)
    with pytest.raises(ValueError, match="not published"):
        service.run(record.id, {})
    service.publish(record.id)
    result = service.run(record.id, {"start": lambda n, v: "ok", "end": lambda n, v: v["start"]})
    assert result.status.value == "SUCCESS"


def test_invalid_dsl_is_not_persisted():
    service = WorkflowService()
    with pytest.raises(ValueError):
        service.create("invalid", {"nodes": [], "edges": []})
    assert service.repository.list() == []
