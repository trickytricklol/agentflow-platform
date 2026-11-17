import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agentflow.api import ApiHandler, MAX_BODY_BYTES
from agentflow.providers import ModelRegistry
from agentflow.security.access import AuthConfig, Principal
from agentflow.security.audit import AuditLogger, Metrics
from agentflow.service import WorkflowService
from agentflow.service.workflow_service import JsonWorkflowRepository


DSL = {"nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}], "edges": [{"source": "start", "target": "end"}]}


@pytest.fixture
def api(tmp_path):
    original = {name: getattr(ApiHandler, name) for name in ("service", "auth", "audit", "metrics", "models", "data_dir")}
    ApiHandler.service = WorkflowService(JsonWorkflowRepository(str(tmp_path / "workflows.json")))
    ApiHandler.auth = AuthConfig(True, {"secret": Principal("tester", {"admin"})})
    ApiHandler.audit = AuditLogger(tmp_path / "audit.jsonl")
    ApiHandler.metrics = Metrics()
    ApiHandler.models = ModelRegistry()
    ApiHandler.data_dir = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        for name, value in original.items():
            setattr(ApiHandler, name, value)


def _request(base, method, path, payload=None, token=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_health_is_public_and_workflows_require_auth(api):
    status, payload = _request(api, "GET", "/health")
    assert status == 200 and payload["status"] == "ok"

    status, payload = _request(api, "GET", "/workflows")
    assert status == 401 and payload["error"] == "Bearer token required"

    status, payload = _request(api, "GET", "/workflows", token="secret")
    assert status == 200 and isinstance(payload, list)


def test_create_list_delete_and_version_summary(api):
    status, created = _request(api, "POST", "/workflows", {"name": "pipeline", "dsl": DSL}, token="secret")
    assert status == 201 and created["version"] == 1

    status, published = _request(api, "POST", f"/workflows/{created['id']}/publish", {}, token="secret")
    assert status == 200 and published["version"] == 1

    status, summaries = _request(api, "GET", "/workflows", token="secret")
    assert status == 200
    assert summaries[0]["node_count"] == 2 and summaries[0]["last_published_at"]

    status, deleted = _request(api, "DELETE", f"/workflows/{created['id']}", token="secret")
    assert status == 200 and deleted["deleted"] is True

    status, payload = _request(api, "GET", "/workflows", token="secret")
    assert status == 200 and payload == []


def test_malformed_json_and_unknown_routes_return_json_errors(api):
    status, payload = _request(api, "POST", "/workflows", token="secret")
    assert status == 400 and "name" in payload["error"]

    status, payload = _request(api, "GET", "/missing", token="secret")
    assert status == 404 and payload["error"] == "not found"


def test_oversized_request_is_rejected_before_body_read(api):
    host, port = api.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=10) as client:
        client.sendall(
            b"POST /workflows HTTP/1.0\r\n"
            b"Authorization: Bearer secret\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {MAX_BODY_BYTES + 1}\r\n\r\n".encode("ascii")
        )
        response = client.recv(4096).decode("utf-8")
    assert "413" in response.splitlines()[0]


def test_sse_stream_emits_node_and_complete(api):
    status, created = _request(api, "POST", "/workflows", {"name": "stream", "dsl": DSL}, token="secret")
    assert status == 201
    status, _ = _request(api, "POST", f"/workflows/{created['id']}/publish", {}, token="secret")
    assert status == 200

    request = urllib.request.Request(
        api + f"/workflows/{created['id']}/run/stream",
        data=json.dumps({"context": {}}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer secret", "Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.headers["Content-Type"].startswith("text/event-stream")
        body = response.read().decode("utf-8")
    assert "event: node" in body
    assert "event: complete" in body
