import pytest

from agentflow.service import PostgresWorkflowRepository


def test_postgres_adapter_reports_optional_dependency_when_unavailable(monkeypatch):
    # This test remains offline and does not require a database server.
    try:
        import psycopg  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="requires psycopg"):
            PostgresWorkflowRepository("postgresql://invalid")
