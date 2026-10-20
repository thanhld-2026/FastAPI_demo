"""Mục 7: Background task gửi email và cache Redis cho danh sách tag."""

import logging

import fakeredis
import pytest
import redis

from app import cache
from app.services import email as email_service


# ---------- Background tasks ----------
@pytest.fixture
def sent_emails(monkeypatch) -> list[dict]:
    """Thay hàm gửi mail thật bằng hàm ghi lại -> kiểm tra được ai nhận mail."""
    outbox: list[dict] = []
    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda to, subject, body: outbox.append({"to": to, "subject": subject, "body": body}),
    )
    return outbox


def test_comment_notifies_task_creator_and_assignee(
    client, make_user, make_project, make_task, sent_emails
):
    pm = make_user("pmuser")
    creator = make_user("creator")
    dev = make_user("dev")
    task = make_task(make_project(pm)["id"], creator, title="Payment API")
    client.post(
        f"/api/tasks/{task['id']}/assign", json={"assignee_id": dev["id"]}, headers=pm["headers"]
    )

    resp = client.post(
        f"/api/tasks/{task['id']}/comments", json={"content": "Please review"}, headers=pm["headers"]
    )

    # TestClient chạy xong background task rồi mới trả về -> kiểm tra ngay được
    assert resp.status_code == 201
    assert sorted(mail["to"] for mail in sent_emails) == ["creator@example.com", "dev@example.com"]
    assert "pmuser commented on task" in sent_emails[0]["subject"]
    assert "Please review" in sent_emails[0]["body"]


def test_commenter_does_not_notify_themselves(
    client, make_user, make_project, make_task, sent_emails
):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)  # pm vừa là creator vừa là người comment

    client.post(f"/api/tasks/{task['id']}/comments", json={"content": "Note"}, headers=pm["headers"])

    assert sent_emails == []


def test_send_email_only_logs_when_disabled(caplog, monkeypatch):
    monkeypatch.setattr(email_service.settings, "EMAIL_ENABLED", False)

    with caplog.at_level(logging.INFO, logger="app.services.email"):
        email_service.send_email("a@example.com", "Hello", "Body")

    assert "email disabled" in caplog.text


# ---------- Cache ----------
@pytest.fixture
def fake_redis(monkeypatch) -> fakeredis.FakeRedis:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "get_redis", lambda: client)
    return client


def test_tags_are_cached_and_invalidated_on_change(client, make_tag, fake_redis):
    make_tag("backend")

    first = client.get("/api/tags")
    second = client.get("/api/tags")
    make_tag("frontend")  # tạo tag mới -> xóa cache
    third = client.get("/api/tags")

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()
    assert third.headers["X-Cache"] == "MISS"
    assert [t["name"] for t in third.json()] == ["backend", "frontend"]
    assert fake_redis.ttl("taskhub:tags:all") > 0  # cache có thời hạn


def test_tags_work_without_redis(client, make_tag):
    make_tag("backend")

    resp = client.get("/api/tags")

    assert resp.status_code == 200
    assert resp.headers["X-Cache"] == "MISS"


def test_tags_fall_back_to_database_when_redis_is_down(client, make_tag, monkeypatch):
    unreachable = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    monkeypatch.setattr(cache, "get_redis", lambda: unreachable)
    make_tag("backend")

    resp = client.get("/api/tags")

    assert resp.status_code == 200
    assert [t["name"] for t in resp.json()] == ["backend"]


def test_only_admin_can_manage_tags(client, make_user):
    member = make_user("member")
    admin = make_user("boss", admin=True)

    forbidden = client.post("/api/tags", json={"name": "x"}, headers=member["headers"])
    created = client.post("/api/tags", json={"name": "  Backend "}, headers=admin["headers"])
    duplicate = client.post("/api/tags", json={"name": "backend"}, headers=admin["headers"])
    deleted = client.delete(f"/api/tags/{created.json()['id']}", headers=admin["headers"])

    assert forbidden.status_code == 403
    assert created.status_code == 201
    assert created.json()["name"] == "backend"  # chuẩn hóa chữ thường + cắt khoảng trắng
    assert duplicate.status_code == 409
    assert deleted.status_code == 204
