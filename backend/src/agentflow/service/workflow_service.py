from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any
import json
from pathlib import Path
import sqlite3

from agentflow.core import WorkflowGraph, WorkflowEngine


@dataclass
class WorkflowRecord:
    id: str
    name: str
    dsl: dict[str, Any]
    version: int = 1
    published: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkflowRepository:
    def __init__(self):
        self._items: dict[str, WorkflowRecord] = {}

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        self._items[record.id] = record
        return record

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        return self._items.get(workflow_id)

    def list(self) -> list[WorkflowRecord]:
        return list(self._items.values())


class JsonWorkflowRepository(WorkflowRepository):
    """Durable local repository for development and single-node deployments."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        super().__init__()
        self._load()

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        result = super().save(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([serialize_record(item) for item in self._items.values()], ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def _load(self) -> None:
        if not self.path.exists():
            return
        for raw in json.loads(self.path.read_text(encoding="utf-8")):
            self._items[raw["id"]] = WorkflowRecord(**raw)


class SqliteWorkflowRepository(WorkflowRepository):
    """SQLite adapter with the same repository contract as the in-memory version."""

    def __init__(self, path: str = "agentflow.db"):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        super().__init__()
        self.connection.execute("CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, dsl TEXT NOT NULL, version INTEGER NOT NULL, published INTEGER NOT NULL, created_at TEXT NOT NULL)")
        self.connection.commit()
        for row in self.connection.execute("SELECT id, name, dsl, version, published, created_at FROM workflows"):
            self._items[row[0]] = WorkflowRecord(row[0], row[1], json.loads(row[2]), row[3], bool(row[4]), row[5])

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        super().save(record)
        self.connection.execute("INSERT OR REPLACE INTO workflows VALUES (?, ?, ?, ?, ?, ?)", (record.id, record.name, json.dumps(record.dsl, ensure_ascii=False), record.version, int(record.published), record.created_at))
        self.connection.commit()
        return record


class PostgresWorkflowRepository(WorkflowRepository):
    """PostgreSQL adapter; requires optional psycopg at deployment time."""

    def __init__(self, dsn: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc
        self.connection = psycopg.connect(dsn)
        super().__init__()
        with self.connection.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, dsl JSONB NOT NULL, version INTEGER NOT NULL, published BOOLEAN NOT NULL, created_at TEXT NOT NULL)")
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id, name, dsl, version, published, created_at FROM workflows")
            for row in cursor.fetchall():
                self._items[row[0]] = WorkflowRecord(row[0], row[1], row[2], row[3], row[4], row[5])

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        super().save(record)
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO workflows (id, name, dsl, version, published, created_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, dsl=EXCLUDED.dsl, version=EXCLUDED.version, published=EXCLUDED.published", (record.id, record.name, json.dumps(record.dsl, ensure_ascii=False), record.version, record.published, record.created_at))
        self.connection.commit()
        return record


class WorkflowService:
    def __init__(self, repository: WorkflowRepository | None = None):
        self.repository = repository or WorkflowRepository()

    def create(self, name: str, dsl: dict[str, Any]) -> WorkflowRecord:
        WorkflowGraph.from_dsl(dsl)  # validate before persistence
        return self.repository.save(WorkflowRecord(str(uuid4()), name, dsl))

    def publish(self, workflow_id: str) -> WorkflowRecord:
        record = self._required(workflow_id)
        WorkflowGraph.from_dsl(record.dsl)
        record.published = True
        return record

    def run(self, workflow_id: str, handlers: dict[str, Any], context: dict[str, Any] | None = None):
        record = self._required(workflow_id)
        if not record.published:
            raise ValueError("workflow is not published")
        return WorkflowEngine(WorkflowGraph.from_dsl(record.dsl), handlers).run(context)

    def _required(self, workflow_id: str) -> WorkflowRecord:
        record = self.repository.get(workflow_id)
        if record is None:
            raise KeyError(f"workflow not found: {workflow_id}")
        return record


def serialize_record(record: WorkflowRecord) -> dict[str, Any]:
    return asdict(record)
