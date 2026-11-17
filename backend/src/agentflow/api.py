from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import urlsplit

from agentflow.service.workflow_service import JsonWorkflowRepository, WorkflowService, serialize_record, serialize_summary
from agentflow.security import AuditLogger, AuthConfig, Metrics, Principal
from agentflow.providers import ModelConfig, ModelRegistry, MockProvider, OllamaProvider, OpenAICompatibleProvider, ModelProvider
from agentflow.nodes import AgentNode, LLMNode, ToolNode


def build_provider():
    """Select the runtime provider from environment configuration."""
    ollama_url = os.getenv("AGENTFLOW_OLLAMA_URL")
    if ollama_url:
        return OllamaProvider(ollama_url, timeout=float(os.getenv("AGENTFLOW_MODEL_TIMEOUT", "120")))
    openai_base = os.getenv("AGENTFLOW_OPENAI_BASE_URL")
    if openai_base:
        return OpenAICompatibleProvider(openai_base, os.getenv("AGENTFLOW_OPENAI_API_KEY", ""), timeout=float(os.getenv("AGENTFLOW_MODEL_TIMEOUT", "120")))
    return MockProvider()


def locate_frontend() -> Path | None:
    """Find the bundled web console in source and container layouts."""
    here = Path(__file__).resolve()
    candidates = [here.parents[3] / "frontend", here.parents[2] / "frontend", Path.cwd() / "frontend"]
    return next((path for path in candidates if path.is_dir()), None)


FRONTEND_DIR = locate_frontend()
STATIC_FILES = {"index.html", "app.js", "styles.css"}
MAX_BODY_BYTES = int(os.getenv("AGENTFLOW_MAX_BODY_BYTES", "1048576"))
CORS_ORIGINS = [item.strip() for item in os.getenv("AGENTFLOW_CORS_ORIGINS", "*").split(",") if item.strip()]


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def build_auth() -> AuthConfig:
    enabled = os.getenv("AGENTFLOW_AUTH_ENABLED", "0") == "1"
    token = os.getenv("AGENTFLOW_API_TOKEN", "")
    if enabled and not token:
        raise RuntimeError("AGENTFLOW_API_TOKEN is required when authentication is enabled")
    return AuthConfig(enabled, {token: Principal("api", {"admin"})} if token else {})


class RoutingProvider(ModelProvider):
    """Dispatch chat calls to a registered model, falling back to the runtime provider."""

    name = "routing"

    def __init__(self, registry: ModelRegistry, fallback: ModelProvider):
        self.registry = registry
        self.fallback = fallback

    def chat(self, messages, *, model: str, temperature: float = 0.0, **kwargs):
        try:
            config, provider = self.registry.get(model)
        except KeyError:
            return self.fallback.chat(messages, model=model, temperature=temperature, **kwargs)
        return provider.chat(messages, model=config.model, temperature=temperature, **kwargs)


class ApiHandler(BaseHTTPRequestHandler):
    timeout = 60
    data_dir = os.getenv("AGENTFLOW_DATA_DIR", ".")
    service = WorkflowService(JsonWorkflowRepository(os.path.join(data_dir, "workflows.json")))
    auth = build_auth()
    audit = AuditLogger(os.path.join(data_dir, "audit.jsonl"))
    metrics = Metrics()
    models = ModelRegistry()
    models.register(ModelConfig("mock-default", "mock", "mock"), MockProvider())
    provider = RoutingProvider(models, build_provider())
    tools = {}
    agents = {}

    def _handlers(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "start": lambda node, values: context,
            "llm": LLMNode(self.provider),
            "tool": ToolNode(self.tools),
            "agent": AgentNode(self.agents),
            "end": lambda node, values: {key: value for key, value in values.items() if key != node.id},
        }

    def _authenticate(self):
        return self.auth.authenticate(self.headers.get("Authorization"))

    def _cors_origin(self) -> str | None:
        if "*" in CORS_ORIGINS:
            return "*"
        origin = self.headers.get("Origin")
        return origin if origin in CORS_ORIGINS else None

    def _security_headers(self, content_type: str | None = None) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type and content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'")

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._response_started = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers("application/json")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self) -> bool:
        if FRONTEND_DIR is None:
            return False
        path = urlsplit(self.path).path
        name = "index.html" if path == "/" else path.lstrip("/")
        if name not in STATIC_FILES:
            return False
        target = FRONTEND_DIR / name
        if not target.is_file():
            return False
        body = target.read_bytes()
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or name.endswith(".js"):
            content_type += "; charset=utf-8"
        self._response_started = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers(content_type)
        self.end_headers()
        self.wfile.write(body)
        return True

    def _payload(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(411, "Content-Length is required")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            length = 0
        else:
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ApiError(400, "invalid Content-Length") from exc
        if length < 0:
            raise ApiError(400, "invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, f"request body exceeds {MAX_BODY_BYTES} bytes")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError(400, "request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "JSON body must be an object")
        return payload

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self._serve_static():
            return
        path = urlsplit(self.path).path
        try:
            if path == "/health":
                return self._json(200, {"status": "ok", "service": "agentflow", "metrics": self.metrics.snapshot()})
            if path == "/ready":
                try:
                    self.service.repository.list()
                    writable = os.access(self.data_dir, os.W_OK)
                except Exception:
                    writable = False
                return self._json(200 if writable else 503, {"status": "ready" if writable else "not-ready"})
            self._authenticate()
            if path == "/metrics":
                return self._json(200, self.metrics.snapshot())
            if path == "/models":
                return self._json(200, self.models.list())
            if path == "/workflows":
                return self._json(200, [serialize_summary(item) for item in self.service.repository.list()])
            if path.startswith("/workflows/") and len(path.split("/")) == 3:
                workflow_id = path.split("/")[2]
                record = self.service.repository.get(workflow_id)
                return self._json(200, serialize_record(record)) if record else self._json(404, {"error": "workflow not found"})
            self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(401, {"error": str(exc)})
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:
            self.log_error("unhandled GET error: %s", exc)
            if not getattr(self, "_response_started", False):
                self._json(500, {"error": "internal server error"})

    def do_PUT(self):
        try:
            principal = self._authenticate()
            payload = self._payload()
            path = urlsplit(self.path).path
            if path.startswith("/workflows/") and len(path.split("/")) == 3:
                workflow_id = path.split("/")[2]
                record = self.service.update(workflow_id, payload.get("name"), payload.get("dsl"))
                self.audit.record("workflow.update", principal.subject, workflow_id)
                return self._json(200, serialize_record(record))
            self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(401, {"error": str(exc)})
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self.log_error("unhandled PUT error: %s", exc)
            if not getattr(self, "_response_started", False):
                self._json(500, {"error": "internal server error"})

    def do_DELETE(self):
        try:
            principal = self._authenticate()
            path = urlsplit(self.path).path
            if path.startswith("/workflows/") and len(path.split("/")) == 3:
                workflow_id = path.split("/")[2]
                record = self.service.delete(workflow_id)
                self.audit.record("workflow.delete", principal.subject, workflow_id, {"name": record.name})
                return self._json(200, {"id": record.id, "deleted": True})
            self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(401, {"error": str(exc)})
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self.log_error("unhandled DELETE error: %s", exc)
            if not getattr(self, "_response_started", False):
                self._json(500, {"error": "internal server error"})

    def do_POST(self):
        try:
            principal = self._authenticate()
            payload = self._payload()
            path = urlsplit(self.path).path
            if path == "/workflows":
                record = self.service.create(payload["name"], payload["dsl"])
                self.audit.record("workflow.create", principal.subject, record.id, {"name": record.name})
                return self._json(201, serialize_record(record))
            if path == "/models":
                provider_name = str(payload["provider"]).lower()
                base_url = payload.get("base_url", "")
                timeout = float(os.getenv("AGENTFLOW_MODEL_TIMEOUT", "120"))
                if provider_name in ("ollama", "ollama-native"):
                    impl = OllamaProvider(base_url or "http://127.0.0.1:11434", timeout=timeout)
                elif provider_name in ("openai", "openai-compatible"):
                    if not base_url:
                        raise ValueError("base_url is required for an OpenAI-compatible model")
                    impl = OpenAICompatibleProvider(base_url, payload.get("api_key", os.getenv("AGENTFLOW_OPENAI_API_KEY", "")), timeout=timeout)
                elif provider_name == "mock":
                    impl = MockProvider(payload.get("test_response", "mock response"))
                else:
                    raise ValueError(f"unsupported provider: {provider_name}")
                config = ModelConfig(payload["name"], payload["provider"], payload["model"], base_url, payload.get("enabled", True))
                self.models.register(config, impl)
                return self._json(201, {"name": config.name, "provider": config.provider, "model": config.model, "enabled": config.enabled})
            if path.startswith("/workflows/") and path.endswith("/publish"):
                workflow_id = path.split("/")[2]
                record = self.service.publish(workflow_id)
                self.audit.record("workflow.publish", principal.subject, workflow_id, {"version": record.version})
                return self._json(200, serialize_record(record))
            if path.startswith("/workflows/") and path.endswith("/rollback"):
                workflow_id = path.split("/")[2]
                record = self.service.rollback(workflow_id, payload.get("version"))
                self.audit.record("workflow.rollback", principal.subject, workflow_id, {"version": record.version})
                return self._json(200, serialize_record(record))
            if path.startswith("/workflows/") and path.endswith("/run/stream"):
                workflow_id = path.split("/")[2]
                record = self.service.repository.get(workflow_id)
                if record is None:
                    return self._json(404, {"error": "workflow not found"})
                if not record.published:
                    return self._json(400, {"error": "workflow is not published"})
                context = payload.get("context") or {}
                if not isinstance(context, dict):
                    raise ValueError("context must be a JSON object")
                self._response_started = True
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                origin = self._cors_origin()
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self._security_headers("text/event-stream")
                self.end_headers()
                write_lock = Lock()
                cancel = Event()
                finished = Event()

                def write_frame(name: str, data: Any) -> bool:
                    if name == "ping":
                        frame = ": ping\n\n"
                    else:
                        frame = f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    with write_lock:
                        try:
                            self.wfile.write(frame.encode("utf-8"))
                            self.wfile.flush()
                            return True
                        except (OSError, ValueError):
                            return False

                def emit(event):
                    if not write_frame("node", {"node_id": event.node_id, "status": event.status.value, "attempt": event.attempt, "error": event.error}):
                        cancel.set()

                def heartbeat():
                    while not finished.wait(15):
                        if not write_frame("ping", None):
                            cancel.set()
                            return

                beat = Thread(target=heartbeat, daemon=True)
                beat.start()
                status = "ERROR"
                error: str | None = None
                try:
                    result = self.service.run(workflow_id, self._handlers(context), context, on_event=emit, cancel_event=cancel)
                    status = result.status.value
                except Exception as exc:
                    error = str(exc)
                finally:
                    finished.set()
                    beat.join(timeout=1)
                if error is None:
                    write_frame("complete", {"status": status, "cancelled": cancel.is_set()})
                else:
                    write_frame("error", {"status": "ERROR", "error": error})
                self.metrics.increment("workflow_runs")
                self.audit.record("workflow.run", principal.subject, workflow_id, {"status": status, "stream": True})
                return
            if path.startswith("/workflows/") and path.endswith("/run"):
                workflow_id = path.split("/")[2]
                context = payload.get("context") or {}
                if not isinstance(context, dict):
                    raise ValueError("context must be a JSON object")
                result = self.service.run(workflow_id, self._handlers(context), context)
                self.metrics.increment("workflow_runs")
                self.audit.record("workflow.run", principal.subject, workflow_id, {"status": result.status.value})
                return self._json(200, {"status": result.status.value, "nodes": {key: {"status": value.status.value, "value": value.value, "error": value.error} for key, value in result.nodes.items()}, "events": [{"node_id": event.node_id, "status": event.status.value, "attempt": event.attempt, "error": event.error} for event in result.events]})
            self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(401, {"error": str(exc)})
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self.log_error("unhandled POST error: %s", exc)
            if not getattr(self, "_response_started", False):
                self._json(500, {"error": "internal server error"})


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or os.getenv("AGENTFLOW_HOST", "127.0.0.1")
    port = int(port or os.getenv("AGENTFLOW_PORT", "8080"))
    ThreadingHTTPServer((host, port), ApiHandler).serve_forever()


if __name__ == "__main__":
    serve()
