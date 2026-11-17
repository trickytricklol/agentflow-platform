from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Callable
import copy
import json
from pathlib import Path
import sqlite3

from agentflow.core import WorkflowGraph, WorkflowEngine, EngineEvent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkflowRecord:
    id: str
    name: str
    dsl: dict[str, Any]
    version: int = 1
    published: bool = False
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    history: list[dict[str, Any]] = field(default_factory=list)


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

    def delete(self, workflow_id: str) -> bool:
        return self._items.pop(workflow_id, None) is not None


class JsonWorkflowRepository(WorkflowRepository):
    """Durable local repository for development and single-node deployments."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        super().__init__()
        self._load()

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        result = super().save(record)
        self._flush()
        return result

    def delete(self, workflow_id: str) -> bool:
        removed = super().delete(workflow_id)
        if removed:
            self._flush()
        return removed

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([serialize_record(item) for item in self._items.values()], ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self.path.exists():
            return
        for raw in json.loads(self.path.read_text(encoding="utf-8")):
            data = dict(raw)
            data.setdefault("updated_at", data.get("created_at", ""))
            data.setdefault("history", [])
            self._items[data["id"]] = WorkflowRecord(**data)


class SqliteWorkflowRepository(WorkflowRepository):
    """SQLite adapter with the same repository contract as the in-memory version."""

    COLUMNS = "id, name, dsl, version, published, created_at, updated_at, history"

    def __init__(self, path: str = "agentflow.db"):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        super().__init__()
        self.connection.execute("CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, dsl TEXT NOT NULL, version INTEGER NOT NULL, published INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT '', history TEXT NOT NULL DEFAULT '[]')")
        self._ensure_columns()
        self.connection.commit()
        for row in self.connection.execute(f"SELECT {self.COLUMNS} FROM workflows"):
            history = json.loads(row[7] or "[]")
            self._items[row[0]] = WorkflowRecord(row[0], row[1], json.loads(row[2]), row[3], bool(row[4]), row[5], row[6] or row[5], history)

    def _ensure_columns(self) -> None:
        existing = {row[1] for row in self.connection.execute("PRAGMA table_info(workflows)")}
        if "updated_at" not in existing:
            self.connection.execute("ALTER TABLE workflows ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        if "history" not in existing:
            self.connection.execute("ALTER TABLE workflows ADD COLUMN history TEXT NOT NULL DEFAULT '[]'")

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        super().save(record)
        self.connection.execute("INSERT OR REPLACE INTO workflows (id, name, dsl, version, published, created_at, updated_at, history) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (record.id, record.name, json.dumps(record.dsl, ensure_ascii=False), record.version, int(record.published), record.created_at, record.updated_at, json.dumps(record.history, ensure_ascii=False)))
        self.connection.commit()
        return record

    def delete(self, workflow_id: str) -> bool:
        removed = super().delete(workflow_id)
        if removed:
            self.connection.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            self.connection.commit()
        return removed


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
            cursor.execute("CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, dsl JSONB NOT NULL, version INTEGER NOT NULL, published BOOLEAN NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT '', history JSONB NOT NULL DEFAULT '[]'::jsonb)")
            cursor.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT ''")
            cursor.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS history JSONB NOT NULL DEFAULT '[]'::jsonb")
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id, name, dsl, version, published, created_at, updated_at, history FROM workflows")
            for row in cursor.fetchall():
                history = row[7] if isinstance(row[7], list) else json.loads(row[7] or "[]")
                self._items[row[0]] = WorkflowRecord(row[0], row[1], row[2], row[3], row[4], row[5], row[6] or row[5], history)

    def save(self, record: WorkflowRecord) -> WorkflowRecord:
        super().save(record)
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO workflows (id, name, dsl, version, published, created_at, updated_at, history) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, dsl=EXCLUDED.dsl, version=EXCLUDED.version, published=EXCLUDED.published, updated_at=EXCLUDED.updated_at, history=EXCLUDED.history", (record.id, record.name, json.dumps(record.dsl, ensure_ascii=False), record.version, record.published, record.created_at, record.updated_at, json.dumps(record.history, ensure_ascii=False)))
        self.connection.commit()
        return record

    def delete(self, workflow_id: str) -> bool:
        removed = super().delete(workflow_id)
        if removed:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM workflows WHERE id = %s", (workflow_id,))
            self.connection.commit()
        return removed


class WorkflowService:
    def __init__(self, repository: WorkflowRepository | None = None):
        self.repository = repository or WorkflowRepository()

    def create(self, name: str, dsl: dict[str, Any]) -> WorkflowRecord:
        WorkflowGraph.from_dsl(dsl)  # validate before persistence
        return self.repository.save(WorkflowRecord(str(uuid4()), name, dsl))

    def update(self, workflow_id: str, name: str | None = None, dsl: dict[str, Any] | None = None) -> WorkflowRecord:
        record = self._required(workflow_id)
        if dsl is not None:
            WorkflowGraph.from_dsl(dsl)
            if dsl != record.dsl:
                record.dsl = dsl
                record.published = False
        if name is not None:
            if not name.strip():
                raise ValueError("workflow name is required")
            record.name = name.strip()
        record.updated_at = _now()
        return self.repository.save(record)

    def publish(self, workflow_id: str) -> WorkflowRecord:
        record = self._required(workflow_id)
        WorkflowGraph.from_dsl(record.dsl)
        if record.published and record.history and record.history[-1].get("dsl") == record.dsl:
            return record
        next_version = max((entry["version"] for entry in record.history), default=record.version - 1) + 1
        record.version = next_version
        record.published = True
        record.updated_at = _now()
        record.history.append({"version": next_version, "dsl": copy.deepcopy(record.dsl), "published_at": record.updated_at})
        record.history = record.history[-50:]
        return self.repository.save(record)

    def rollback(self, workflow_id: str, version: int | None = None) -> WorkflowRecord:
        record = self._required(workflow_id)
        if not record.history:
            raise ValueError("workflow has no published version to roll back to")
        if version is None:
            if record.published and record.history[-1].get("version") == record.version and len(record.history) > 1:
                target = record.history[-2]
            else:
                target = record.history[-1]
        else:
            target = next((entry for entry in reversed(record.history) if entry.get("version") == version), None)
            if target is None:
                raise ValueError(f"version not found: {version}")
        if target.get("dsl") == record.dsl and record.published:
            return record
        record.dsl = copy.deepcopy(target["dsl"])
        record.published = True
        record.version = max(entry["version"] for entry in record.history) + 1
        record.updated_at = _now()
        record.history.append({"version": record.version, "dsl": copy.deepcopy(record.dsl), "published_at": record.updated_at})
        record.history = record.history[-50:]
        return self.repository.save(record)

    def run(self, workflow_id: str, handlers: dict[str, Any], context: dict[str, Any] | None = None, on_event: Callable[[EngineEvent], None] | None = None):
        record = self._required(workflow_id)
        if not record.published:
            raise ValueError("workflow is not published")
        return WorkflowEngine(WorkflowGraph.from_dsl(record.dsl), handlers).run(context, on_event=on_event)

    def delete(self, workflow_id: str) -> WorkflowRecord:
        record = self._required(workflow_id)
        self.repository.delete(workflow_id)
        return record

    def _required(self, workflow_id: str) -> WorkflowRecord:
        record = self.repository.get(workflow_id)
        if record is None:
            raise KeyError(f"workflow not found: {workflow_id}")
        return record


def serialize_record(record: WorkflowRecord) -> dict[str, Any]:
    return asdict(record)
