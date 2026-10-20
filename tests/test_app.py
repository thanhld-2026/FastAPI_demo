"""Mục 8: Health check, CORS, request id, xử lý lỗi toàn cục."""

from fastapi.testclient import TestClient

from app import crud
from app.main import app


def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


def test_every_response_has_request_id(client):
    generated = client.get("/health")
    forwarded = client.get("/health", headers={"X-Request-ID": "abc123"})

    assert generated.headers["X-Request-ID"]
    assert forwarded.headers["X-Request-ID"] == "abc123"


def test_cors_allows_configured_frontend_origin(client):
    resp = client.options(
        "/api/projects",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(client):
    resp = client.options(
        "/api/projects",
        headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in resp.headers


def test_unhandled_error_returns_generic_500(client, monkeypatch):
    def broken_list_tags(db):
        raise RuntimeError("database exploded: SELECT * FROM secret_table")

    monkeypatch.setattr(crud.tag, "list_tags", broken_list_tags)
    # raise_server_exceptions=False: nhận response 500 như client thật thay vì exception.
    # (fixture `client` đã override get_db nên client này cũng dùng DB test)
    safe_client = TestClient(app, raise_server_exceptions=False)

    resp = safe_client.get("/api/tags", headers={"X-Request-ID": "req-500"})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error", "request_id": "req-500"}
    assert "secret_table" not in resp.text  # không lộ chi tiết lỗi nội bộ
