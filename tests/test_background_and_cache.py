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
    client, make_user, make_project, make_task, add_member, sent_emails
):
    pm = make_user("pmuser")
    creator = make_user("creator")
    dev = make_user("dev")
    project = make_project(pm)
    add_member(project, pm, creator)
    add_member(project, pm, dev)
    task = make_task(project["id"], creator, title="Payment API")
    client.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"assignee_id": dev["id"]}, headers=pm["headers"]
    )

    resp = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"content": "Please review"},
        headers=pm["headers"],
    )

    # TestClient chạy xong background task rồi mới trả về -> kiểm tra ngay được
    assert resp.status_code == 201
    assert sorted(mail["to"] for mail in sent_emails) == ["creator@example.com", "dev@example.com"]
    assert "pmuser commented on task" in sent_emails[0]["subject"]
    assert "Please review" in sent_emails[0]["body"]


def test_comment_does_not_notify_users_who_left_the_workspace(
    client, make_user, make_project, make_task, add_member, sent_emails
):
    pm = make_user("pmuser")
    creator = make_user("creator")
    project = make_project(pm)
    add_member(project, pm, creator)
    task = make_task(project["id"], creator)
    client.delete(
        f"/api/v1/workspaces/{project['workspace_id']}/members/{creator['id']}",
        headers=creator["headers"],
    )

    client.post(
        f"/api/v1/tasks/{task['id']}/comments", json={"content": "Note"}, headers=pm["headers"]
    )

    assert sent_emails == []  # đã rời workspace thì không nhận nội dung task nữa


def test_commenter_does_not_notify_themselves(
    client, make_user, make_project, make_task, sent_emails
):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)  # pm vừa là creator vừa là người comment

    client.post(
        f"/api/v1/tasks/{task['id']}/comments", json={"content": "Note"}, headers=pm["headers"]
    )

    assert sent_emails == []


def test_send_email_only_logs_when_disabled(caplog, monkeypatch):
    monkeypatch.setattr(email_service.settings, "EMAIL_ENABLED", False)

    with caplog.at_level(logging.INFO, logger="app.services.email"):
        email_service.send_email("a@example.com", "Hello", "Body")

    assert "email disabled" in caplog.text


def test_send_email_logs_instead_of_crashing_on_invalid_header(caplog, monkeypatch):
    """Subject có ký tự xuống dòng -> header không hợp lệ: chỉ ghi log, task không chết."""
    monkeypatch.setattr(email_service.settings, "EMAIL_ENABLED", True)

    with caplog.at_level(logging.ERROR, logger="app.services.email"):
        email_service.send_email("a@example.com", "Hello\nInjected: header", "Body")

    assert "Failed to send email" in caplog.text


# ---------- Cache ----------
@pytest.fixture
def fake_redis(monkeypatch) -> fakeredis.FakeRedis:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "get_redis", lambda: client)
    return client


def test_tags_are_cached_and_invalidated_on_change(client, make_user, make_tag, fake_redis):
    headers = make_user("alice")["headers"]
    make_tag("backend")

    first = client.get("/api/v1/tags", headers=headers)
    second = client.get("/api/v1/tags", headers=headers)
    make_tag("frontend")  # tạo tag mới -> xóa cache
    third = client.get("/api/v1/tags", headers=headers)

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()
    assert third.headers["X-Cache"] == "MISS"
    assert [t["name"] for t in third.json()] == ["backend", "frontend"]
    assert fake_redis.ttl("taskhub:tags:all") > 0  # cache có thời hạn


def test_tags_work_without_redis(client, make_user, make_tag):
    headers = make_user("alice")["headers"]
    make_tag("backend")

    resp = client.get("/api/v1/tags", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["X-Cache"] == "MISS"


def test_tags_fall_back_to_database_when_redis_is_down(
    client, make_user, make_tag, monkeypatch
):
    headers = make_user("alice")["headers"]
    unreachable = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    monkeypatch.setattr(cache, "get_redis", lambda: unreachable)
    make_tag("backend")

    resp = client.get("/api/v1/tags", headers=headers)

    assert resp.status_code == 200
    assert [t["name"] for t in resp.json()] == ["backend"]


def test_only_admin_can_manage_tags(client, make_user):
    member = make_user("member")
    admin = make_user("boss", admin=True)

    forbidden = client.post("/api/v1/tags", json={"name": "x"}, headers=member["headers"])
    created = client.post("/api/v1/tags", json={"name": "  Backend "}, headers=admin["headers"])
    duplicate = client.post("/api/v1/tags", json={"name": "backend"}, headers=admin["headers"])
    deleted = client.delete(f"/api/v1/tags/{created.json()['id']}", headers=admin["headers"])

    assert forbidden.status_code == 403
    assert created.status_code == 201
    assert created.json()["name"] == "backend"  # chuẩn hóa chữ thường + cắt khoảng trắng
    assert duplicate.status_code == 409
    assert deleted.status_code == 204
