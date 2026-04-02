from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agentflow.service.workflow_service import JsonWorkflowRepository, WorkflowService, serialize_record
from agentflow.security import AuditLogger, AuthConfig, Metrics, Principal
from agentflow.providers import ModelConfig, ModelRegistry, MockProvider


class ApiHandler(BaseHTTPRequestHandler):
    service = WorkflowService(JsonWorkflowRepository("workflows.json"))
    auth = AuthConfig(os.getenv("AGENTFLOW_AUTH_ENABLED", "0") == "1", {os.getenv("AGENTFLOW_API_TOKEN", "dev-token"): Principal("api", {"admin"})})
    audit = AuditLogger("audit.jsonl")
    metrics = Metrics()
    models = ModelRegistry()
    models.register(ModelConfig("mock-default", "mock", "mock"), MockProvider())

    def _authenticate(self):
        return self.auth.authenticate(self.headers.get("Authorization"))

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            self._authenticate()
        except PermissionError as exc:
            return self._json(401, {"error": str(exc)})
        if self.path == "/health":
            return self._json(200, {"status": "ok", "metrics": self.metrics.snapshot()})
        if self.path == "/models":
            return self._json(200, self.models.list())
        if self.path == "/workflows":
            return self._json(200, [serialize_record(item) for item in self.service.repository.list()])
        if self.path.startswith("/workflows/"):
            workflow_id = self.path.split("/")[2]
            record = self.service.repository.get(workflow_id)
            return self._json(200, serialize_record(record)) if record else self._json(404, {"error": "workflow not found"})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            principal = self._authenticate()
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/workflows":
                record = self.service.create(payload["name"], payload["dsl"])
                self.audit.record("workflow.create", principal.subject, record.id, {"name": record.name})
                return self._json(201, serialize_record(record))
            if self.path == "/models":
                config = ModelConfig(payload["name"], payload["provider"], payload["model"], payload.get("base_url", ""), payload.get("enabled", True))
                self.models.register(config, MockProvider(payload.get("test_response", "mock response")))
                return self._json(201, {"name": config.name, "provider": config.provider, "model": config.model, "enabled": config.enabled})
            if self.path.startswith("/workflows/") and self.path.endswith("/publish"):
                workflow_id = self.path.split("/")[2]
                record = self.service.publish(workflow_id)
                self.audit.record("workflow.publish", principal.subject, workflow_id)
                return self._json(200, serialize_record(record))
            if self.path.startswith("/workflows/") and self.path.endswith("/run"):
                workflow_id = self.path.split("/")[2]
                handlers = {
                    "start": lambda node, values: payload.get("context", {}),
                    "llm": lambda node, values: {"content": node.config.get("prompt", "")},
                    "tool": lambda node, values: node.config.get("result"),
                    "agent": lambda node, values: node.config.get("result"),
                    "end": lambda node, values: values,
                }
                result = self.service.run(workflow_id, handlers, payload.get("context", {}))
                self.metrics.increment("workflow_runs")
                self.audit.record("workflow.run", principal.subject, workflow_id, {"status": result.status.value})
                return self._json(200, {"status": result.status.value, "nodes": {key: {"status": value.status.value, "value": value.value, "error": value.error} for key, value in result.nodes.items()}, "events": [{"node_id": event.node_id, "status": event.status.value, "attempt": event.attempt, "error": event.error} for event in result.events]})
            if self.path.startswith("/workflows/") and self.path.endswith("/run/stream"):
                workflow_id = self.path.split("/")[2]
                handlers = {"start": lambda node, values: payload.get("context", {}), "llm": lambda node, values: {"content": node.config.get("prompt", "")}, "tool": lambda node, values: node.config.get("result"), "agent": lambda node, values: node.config.get("result"), "end": lambda node, values: values}
                result = self.service.run(workflow_id, handlers, payload.get("context", {}))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                for event in result.events:
                    data = {"node_id": event.node_id, "status": event.status.value, "attempt": event.attempt, "error": event.error}
                    self.wfile.write(("event: node\\ndata: " + json.dumps(data, ensure_ascii=False) + "\\n\\n").encode("utf-8"))
                    self.wfile.flush()
                self.wfile.write(("event: complete\\ndata: " + json.dumps({"status": result.status.value}) + "\\n\\n").encode("utf-8"))
                self.wfile.flush()
                return
            self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(401, {"error": str(exc)})
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    ThreadingHTTPServer((host, port), ApiHandler).serve_forever()


if __name__ == "__main__":
    serve()
