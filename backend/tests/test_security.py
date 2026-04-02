import pytest

from agentflow.security import AuditLogger, AuthConfig, Metrics, Principal, authorize


def test_auth_and_rbac():
    principal = Principal("u1", {"operator"})
    authorize(principal, "operator")
    with pytest.raises(PermissionError):
        authorize(principal, "admin")
    config = AuthConfig(True, {"secret": principal})
    assert config.authenticate("Bearer secret").subject == "u1"
    with pytest.raises(PermissionError):
        config.authenticate("Bearer bad")


def test_audit_and_metrics(tmpdir):
    logger = AuditLogger(tmpdir.join("audit.jsonl"))
    logger.record("workflow.run", "u1", "w1", {"status": "SUCCESS"})
    assert len(logger.events) == 1
    metrics = Metrics()
    metrics.increment("workflow_runs")
    metrics.increment("workflow_runs", 2)
    assert metrics.snapshot()["workflow_runs"] == 3
