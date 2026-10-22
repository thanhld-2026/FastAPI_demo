"""Mục 8: Health check, CORS, request id, xử lý lỗi toàn cục."""

from app import crud
from app.config import Settings


def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


def test_every_response_has_request_id(client):
    generated = client.get("/health")
    forwarded = client.get("/health", headers={"X-Request-ID": "abc123"})

    assert generated.headers["X-Request-ID"]
    assert forwarded.headers["X-Request-ID"] == "abc123"


def test_invalid_request_id_from_client_is_replaced(client):
    too_long = client.get("/health", headers={"X-Request-ID": "a" * 500})
    weird_chars = client.get("/health", headers={"X-Request-ID": "abc;DROP TABLE"})

    for resp in (too_long, weird_chars):
        request_id = resp.headers["X-Request-ID"]
        assert len(request_id) == 12 and request_id.isalnum()  # id tự sinh


def test_cors_allows_configured_frontend_origin(client):
    resp = client.options(
        "/api/v1/projects",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(client):
    resp = client.options(
        "/api/v1/projects",
        headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in resp.headers


def test_unhandled_error_returns_generic_500(client, make_user, make_project, monkeypatch):
    pm = make_user("pmuser")
    project = make_project(pm)

    def broken_list(db, project_id):
        raise RuntimeError("database exploded: SELECT * FROM secret_table")

    monkeypatch.setattr(crud.label, "list_for_project", broken_list)

    resp = client.get(
        f"/api/v1/projects/{project['id']}/labels",
        headers={**pm["headers"], "X-Request-ID": "req-500", "Origin": "http://localhost:3000"},
    )

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error", "request_id": "req-500"}
    assert "secret_table" not in resp.text  # không lộ chi tiết lỗi nội bộ
    # Response 500 vẫn đi qua CORS + middleware log -> FE đọc được lỗi và request id
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert resp.headers["X-Request-ID"] == "req-500"


def test_old_tags_cache_ttl_setting_is_still_read(monkeypatch):
    """Biến môi trường đổi tên (tag -> label): .env cũ vẫn dùng được, không bị bỏ qua âm thầm."""
    monkeypatch.delenv("LABELS_CACHE_TTL", raising=False)
    monkeypatch.setenv("TAGS_CACHE_TTL", "42")

    assert Settings(_env_file=None).LABELS_CACHE_TTL == 42
