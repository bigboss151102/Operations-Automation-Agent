"""REST API smoke tests (plan Phase 7). The agent itself is covered by test_agent.py."""

import pytest
from fastapi.testclient import TestClient

from src.api import routes
from src.common.schemas import AnalyzeResponse, ResponseStatus
from src.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def calls(monkeypatch) -> list[tuple[str, list[str]]]:
    recorded: list[tuple[str, list[str]]] = []

    def fake_run_agent(message: str, history: list[str] | None = None) -> AnalyzeResponse:
        recorded.append((message, list(history or [])))
        return AnalyzeResponse(request_id="req-test", thread_id="req-test", status=ResponseStatus.NOT_FOUND)

    monkeypatch.setattr(routes, "run_agent", fake_run_agent)
    return recorded


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_returns_response_shape(client, calls):
    response = client.post("/api/v1/agent/analyze", json={"message": "Please check order ORD-9999."})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_found"
    assert body["request_id"] == "req-test"
    assert {"recommended_actions", "executed_actions", "approvals", "customer_response"} <= body.keys()


def test_analyze_passes_history_to_service(client, calls):
    client.post(
        "/api/v1/agent/analyze",
        json={"message": " It's ORD-1007. ", "history": ["My order hasn't arrived and I want a refund."]},
    )
    assert calls == [("It's ORD-1007.", ["My order hasn't arrived and I want a refund."])]  # whitespace stripped


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 2001},
        {},
        {"message": "ok", "unexpected": True},
        {"message": "ok", "history": ["h"] * 11},
    ],
)
def test_analyze_rejects_invalid_bodies(client, calls, body):
    assert client.post("/api/v1/agent/analyze", json=body).status_code == 422
    assert calls == []  # the agent never ran


def test_unexpected_error_returns_safe_envelope(client, monkeypatch):
    def boom(message: str, history: list[str] | None = None) -> AnalyzeResponse:
        raise RuntimeError("secret stack detail sk-should-not-leak")

    monkeypatch.setattr(routes, "run_agent", boom)
    response = client.post("/api/v1/agent/analyze", json={"message": "hello"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert "Traceback" not in response.text


def test_openapi_documents_the_contract(client):
    schema = client.get("/openapi.json").json()
    assert "/api/v1/agent/analyze" in schema["paths"]
    assert "AnalyzeResponse" in schema["components"]["schemas"]
