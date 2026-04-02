from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass
class AuditEvent:
    action: str
    subject: str
    resource: str
    detail: dict[str, Any]
    timestamp: str


class AuditLogger:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[AuditEvent] = []

    def record(self, action: str, subject: str, resource: str, detail: dict[str, Any] | None = None) -> AuditEvent:
        event = AuditEvent(action, subject, resource, detail or {}, datetime.now(timezone.utc).isoformat())
        self.events.append(event)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        return event


class Metrics:
    def __init__(self):
        self.counters = Counter()

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
