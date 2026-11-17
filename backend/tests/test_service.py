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


def test_update_publish_and_rollback_versions():
    service = WorkflowService()
    record = service.create("versioned", DSL)
    first = service.publish(record.id)
    assert first.version == 1 and len(first.history) == 1
    assert service.publish(record.id).version == 1

    changed = {"nodes": [{"id": "start", "type": "start"}, {"id": "work", "type": "tool"}, {"id": "end", "type": "end"}], "edges": [{"source": "start", "target": "work"}, {"source": "work", "target": "end"}]}
    updated = service.update(record.id, dsl=changed)
    assert updated.published is False and updated.version == 1

    second = service.publish(record.id)
    assert second.version == 2 and len(second.history) == 2
    assert second.history[-1]["dsl"] == changed

    rolled = service.rollback(record.id)
    assert rolled.version == 3 and rolled.dsl == DSL
    assert len(rolled.history) == 3

    target = service.rollback(record.id, version=2)
    assert target.dsl == changed and target.version == 4


def test_delete_removes_workflow():
    service = WorkflowService()
    record = service.create("temporary", DSL)
    assert service.delete(record.id).id == record.id
    assert service.repository.get(record.id) is None
    assert service.repository.list() == []
    with pytest.raises(KeyError, match="workflow not found"):
        service.delete(record.id)
