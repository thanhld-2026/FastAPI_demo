"""Mục 7 + phụ lục 9, 10: email chạy ngầm (comment, được giao task), cache Redis cho danh sách
label và danh sách task của project."""

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

import fakeredis
import pytest
import redis
from pydantic import BaseModel

from app import cache, crud
from app.models import ActivityAction, Comment, Label, Task, TaskActivity, User
from app.schemas.common import Page
from app.schemas.task import TaskOut
from app.services import email as email_service
from app.services import labels as label_service
from app.services import task_cache


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
    sent_emails.clear()  # bỏ email "được giao task" của bước chuẩn bị

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


def _assign(client, task: dict, assignee: dict | None, by: dict):
    body = {"assignee_id": assignee["id"] if assignee else None}
    return client.post(f"/api/v1/tasks/{task['id']}/assign", json=body, headers=by["headers"])


def test_assignee_gets_an_email(
    client, make_user, make_project, make_task, add_member, sent_emails
):
    owner = make_user("owner")
    dev = make_user("dev")
    project = make_project(owner, name="Mobile App")
    add_member(project, owner, dev)
    task = make_task(project["id"], owner, title="Login screen", priority="HIGH")

    resp = _assign(client, task, dev, by=owner)

    # TestClient chạy xong background task rồi mới trả về -> kiểm tra ngay được
    assert resp.status_code == 200
    assert [mail["to"] for mail in sent_emails] == ["dev@example.com"]
    assert sent_emails[0]["subject"] == (
        f"[TaskHub] owner assigned you task #{task['id']}: Login screen"
    )
    assert "Project: Mobile App" in sent_emails[0]["body"]
    assert "Priority: HIGH" in sent_emails[0]["body"]


def test_no_assign_email_when_nothing_new_for_the_assignee(
    client, make_user, make_project, make_task, add_member, sent_emails
):
    owner = make_user("owner")
    dev = make_user("dev")
    project = make_project(owner)
    add_member(project, owner, dev)
    task = make_task(project["id"], owner)

    _assign(client, task, owner, by=owner)  # tự giao cho mình
    _assign(client, task, dev, by=owner)  # -> 1 email cho dev
    _assign(client, task, dev, by=owner)  # giao lại đúng người đang làm
    _assign(client, task, None, by=owner)  # bỏ assign

    assert [mail["to"] for mail in sent_emails] == ["dev@example.com"]


def test_no_assign_email_when_assign_is_rolled_back(
    client, make_user, make_project, make_task, add_member, sent_emails, monkeypatch
):
    owner = make_user("owner")
    dev = make_user("dev")
    project = make_project(owner)
    add_member(project, owner, dev)
    task = make_task(project["id"], owner)

    def broken_add(*args, **kwargs):
        raise RuntimeError("simulated failure while writing activity")

    monkeypatch.setattr(crud.activity, "add", broken_add)
    resp = _assign(client, task, dev, by=owner)

    assert resp.status_code == 500
    assert sent_emails == []  # không lưu được thì không báo


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


def test_labels_are_cached_per_project_and_invalidated_on_change(
    client, make_user, make_project, make_label, fake_redis
):
    pm = make_user("pmuser")
    project = make_project(pm)
    other = make_project(pm, name="Other")
    make_label(project, pm, "backend")
    make_label(other, pm, "mobile")
    url = f"/api/v1/projects/{project['id']}/labels"
    other_url = f"/api/v1/projects/{other['id']}/labels"
    headers = pm["headers"]

    first = client.get(url, headers=headers)
    second = client.get(url, headers=headers)
    client.get(other_url, headers=headers)  # nạp cache project khác
    make_label(project, pm, "frontend")  # label mới -> chỉ xóa cache của project này
    third = client.get(url, headers=headers)
    other_again = client.get(other_url, headers=headers)

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()
    assert third.headers["X-Cache"] == "MISS"
    assert [lb["name"] for lb in third.json()] == ["backend", "frontend"]
    assert other_again.headers["X-Cache"] == "HIT"  # project khác không bị ảnh hưởng
    data_keys = fake_redis.keys(f"taskhub:projects:{project['id']}:labels:v[0-9]*")
    assert data_keys and all(fake_redis.ttl(key) > 0 for key in data_keys)  # cache có thời hạn


def test_slow_reader_cannot_put_old_labels_back_into_cache(
    client, db, make_user, make_project, make_label, fake_redis, monkeypatch
):
    """Request A đọc DB (danh sách cũ), trong lúc đó B thêm label + làm mới cache, rồi A mới ghi
    cache: dữ liệu cũ của A không được che mất label của B ở các lần đọc sau."""
    pm = make_user("pmuser")
    project = make_project(pm)
    make_label(project, pm, "backend")
    url = f"/api/v1/projects/{project['id']}/labels"
    original = crud.label.list_for_project

    def slow_read(session, project_id):
        labels = original(session, project_id)  # A đọc xong danh sách cũ...
        db.add(Label(project_id=project_id, name="frontend", color="#000000"))
        db.commit()
        label_service.invalidate_cache(project_id)  # ...thì B thêm label, commit, làm mới cache
        return labels

    monkeypatch.setattr(crud.label, "list_for_project", slow_read)
    stale = client.get(url, headers=pm["headers"])
    monkeypatch.setattr(crud.label, "list_for_project", original)
    fresh = client.get(url, headers=pm["headers"])

    assert [lb["name"] for lb in stale.json()] == ["backend"]
    assert fresh.headers["X-Cache"] == "MISS"
    assert [lb["name"] for lb in fresh.json()] == ["backend", "frontend"]


def test_deleted_project_leaves_no_label_cache_behind(
    client, make_user, make_project, make_label, fake_redis
):
    pm = make_user("pmuser")
    project = make_project(pm)
    make_label(project, pm, "old")
    url = f"/api/v1/projects/{project['id']}/labels"
    client.get(url, headers=pm["headers"])  # nạp cache

    client.delete(f"/api/v1/projects/{project['id']}", headers=pm["headers"])
    # SQLite cấp lại id vừa xóa cho project mới: cache cũ mà còn thì project mới thấy label "old"
    reborn = make_project(pm, name="New", workspace={"id": project["workspace_id"]})
    resp = client.get(f"/api/v1/projects/{reborn['id']}/labels", headers=pm["headers"])

    assert reborn["id"] == project["id"]
    assert (resp.headers["X-Cache"], resp.json()) == ("MISS", [])


def test_labels_work_without_redis(client, make_user, make_project, make_label):
    pm = make_user("pmuser")
    project = make_project(pm)
    make_label(project, pm, "backend")

    resp = client.get(f"/api/v1/projects/{project['id']}/labels", headers=pm["headers"])

    assert resp.status_code == 200
    assert resp.headers["X-Cache"] == "MISS"


def test_labels_fall_back_to_database_when_redis_is_down(
    client, make_user, make_project, make_label, monkeypatch
):
    unreachable = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    monkeypatch.setattr(cache, "get_redis", lambda: unreachable)
    pm = make_user("pmuser")
    project = make_project(pm)
    make_label(project, pm, "backend")

    resp = client.get(f"/api/v1/projects/{project['id']}/labels", headers=pm["headers"])

    assert resp.status_code == 200
    assert [lb["name"] for lb in resp.json()] == ["backend"]


# ---------- Cache danh sách task của project (phụ lục feature 9) ----------
@dataclass
class TaskCacheSetup:
    owner: dict
    dev: dict
    project: dict
    other_project: dict
    task: dict
    label: dict
    other_label: dict

    def url(self, project: dict | None = None) -> str:
        return f"/api/v1/projects/{(project or self.project)['id']}/tasks"


@pytest.fixture
def task_cache_setup(
    client, make_user, make_project, make_task, make_label, add_member
) -> TaskCacheSetup:
    """2 project cùng 1 workspace; dev (EDITOR) tạo và đang được giao 1 task có label `bug`,
    project còn label `docs` chưa gắn vào đâu."""
    owner = make_user("owner")
    dev = make_user("dev")
    project = make_project(owner)
    other_project = make_project(owner, name="Other", workspace={"id": project["workspace_id"]})
    add_member(project, owner, dev)
    label = make_label(project, owner, "bug")
    other_label = make_label(project, owner, "docs")
    task = make_task(project["id"], dev, title="Login API", label_ids=[label["id"]])
    make_task(other_project["id"], owner, title="Other task")
    setup = TaskCacheSetup(owner, dev, project, other_project, task, label, other_label)
    _assign(client, task, dev, by=owner)
    return setup


def test_project_tasks_are_cached_per_filter_and_page(client, task_cache_setup, fake_redis):
    s = task_cache_setup
    headers = s.owner["headers"]

    first = client.get(s.url(), headers=headers)
    second = client.get(s.url(), headers=headers)
    todo = [client.get(s.url(), params={"status": "TODO"}, headers=headers) for _ in range(2)]

    assert [r.headers["X-Cache"] for r in (first, second, *todo)] == [
        "MISS",
        "HIT",
        "MISS",  # mỗi tổ hợp filter / trang là 1 key riêng
        "HIT",
    ]
    # HIT trả nguyên chuỗi JSON đã lưu: giống hệt từng byte lần MISS
    assert second.content == first.content
    assert second.headers["content-type"] == "application/json"
    assert [t["title"] for t in second.json()["items"]] == ["Login API"]
    data_keys = fake_redis.keys(f"taskhub:projects:{s.project['id']}:tasks:v[0-9]*")
    assert len(data_keys) == 2 and all(fake_redis.ttl(key) > 0 for key in data_keys)


def test_empty_task_pages_are_not_cached(client, make_user, task_cache_setup, fake_redis):
    """assignee_id / page tùy ý không được tạo ra vô số key rỗng trong Redis."""
    s = task_cache_setup
    outsider = make_user("outsider")
    headers = s.owner["headers"]
    queries = [{"status": "DONE"}, {"page": 99}, {"assignee_id": outsider["id"]}]

    for params in queries:
        for _ in range(2):
            resp = client.get(s.url(), params=params, headers=headers)
            assert (resp.json()["items"], resp.headers["X-Cache"]) == ([], "MISS")

    assert fake_redis.keys(f"taskhub:projects:{s.project['id']}:tasks:v[0-9]*") == []


def test_project_tasks_can_be_filtered_by_assignee(client, task_cache_setup):
    s = task_cache_setup
    _assign(client, s.task, s.dev, by=s.owner)

    mine = client.get(s.url(), params={"assignee_id": s.dev["id"]}, headers=s.owner["headers"])
    nobody = client.get(s.url(), params={"assignee_id": s.owner["id"]}, headers=s.owner["headers"])

    assert [t["title"] for t in mine.json()["items"]] == ["Login API"]
    assert nobody.json()["items"] == []


# Mọi thao tác làm danh sách task của project đổi: (tên, hàm thực hiện)
CHANGES: list = [
    pytest.param(
        lambda c, s: c.post(s.url(), json={"title": "New"}, headers=s.owner["headers"]),
        id="create-task",
    ),
    pytest.param(
        lambda c, s: c.put(
            f"/api/v1/tasks/{s.task['id']}", json={"status": "DONE"}, headers=s.owner["headers"]
        ),
        id="update-task",
    ),
    pytest.param(
        lambda c, s: c.delete(f"/api/v1/tasks/{s.task['id']}", headers=s.owner["headers"]),
        id="delete-task",
    ),
    pytest.param(lambda c, s: _assign(c, s.task, s.owner, by=s.owner), id="reassign"),
    pytest.param(
        lambda c, s: c.post(
            f"/api/v1/tasks/{s.task['id']}/labels/{s.other_label['id']}", headers=s.owner["headers"]
        ),
        id="attach-label",
    ),
    pytest.param(
        lambda c, s: c.delete(
            f"/api/v1/tasks/{s.task['id']}/labels/{s.label['id']}", headers=s.owner["headers"]
        ),
        id="detach-label",
    ),
    pytest.param(
        lambda c, s: c.patch(
            f"/api/v1/labels/{s.label['id']}", json={"name": "defect"}, headers=s.owner["headers"]
        ),
        id="rename-label",
    ),
    pytest.param(
        lambda c, s: c.delete(f"/api/v1/labels/{s.label['id']}", headers=s.owner["headers"]),
        id="delete-label",
    ),
    pytest.param(
        # dev là người tạo task: TaskOut có full_name của dev
        lambda c, s: c.patch(
            "/api/v1/users/me", json={"full_name": "Dev Renamed"}, headers=s.dev["headers"]
        ),
        id="rename-creator",
    ),
    pytest.param(
        # dev bị hạ xuống VIEWER -> task dev đang làm được bỏ assign
        lambda c, s: c.patch(
            f"/api/v1/workspaces/{s.project['workspace_id']}/members/{s.dev['id']}",
            json={"role": "VIEWER"},
            headers=s.owner["headers"],
        ),
        id="demote-assignee",
    ),
]


@pytest.mark.parametrize("change", CHANGES)
def test_project_task_cache_is_refreshed_after_every_change(
    client, task_cache_setup, fake_redis, change: Callable
):
    s = task_cache_setup
    headers = s.owner["headers"]
    before = client.get(s.url(), headers=headers).json()
    client.get(s.url(s.other_project), headers=headers)  # nạp cache project khác

    resp = change(client, s)
    after = client.get(s.url(), headers=headers)
    other = client.get(s.url(s.other_project), headers=headers)

    assert resp.status_code < 300, resp.text
    assert after.headers["X-Cache"] == "MISS"
    assert after.json() != before  # đọc lại từ DB, thấy thay đổi
    assert other.headers["X-Cache"] == "HIT"  # project khác không bị ảnh hưởng


def test_unassigning_a_removed_member_refreshes_the_task_cache(
    client, task_cache_setup, fake_redis
):
    s = task_cache_setup
    headers = s.owner["headers"]
    _assign(client, s.task, s.dev, by=s.owner)
    client.get(s.url(), headers=headers)

    members_url = f"/api/v1/workspaces/{s.project['workspace_id']}/members"
    client.delete(f"{members_url}/{s.dev['id']}", headers=headers)
    after = client.get(s.url(), headers=headers)

    assert after.headers["X-Cache"] == "MISS"
    assert after.json()["items"][0]["assignee"] is None


def test_changes_outside_the_task_list_keep_the_cache(client, task_cache_setup, fake_redis):
    """Comment, bookmark không đổi nội dung danh sách task -> cache vẫn dùng được."""
    s = task_cache_setup
    headers = s.owner["headers"]
    task_url = f"/api/v1/tasks/{s.task['id']}"
    client.get(s.url(), headers=headers)

    client.post(f"{task_url}/comments", json={"content": "LGTM"}, headers=headers)
    client.post(f"{task_url}/bookmark", headers=headers)

    assert client.get(s.url(), headers=headers).headers["X-Cache"] == "HIT"


def test_failed_write_does_not_refresh_the_task_cache(
    client, task_cache_setup, fake_redis, monkeypatch
):
    """Request lỗi giữa chừng -> rollback -> không có gì đổi -> không cần làm mới cache."""
    s = task_cache_setup
    headers = s.owner["headers"]
    client.get(s.url(), headers=headers)

    def broken_add(*args, **kwargs):
        raise RuntimeError("simulated failure while writing activity")

    monkeypatch.setattr(crud.activity, "add", broken_add)
    failed = _assign(client, s.task, s.owner, by=s.owner)

    assert failed.status_code == 500
    assert client.get(s.url(), headers=headers).headers["X-Cache"] == "HIT"


def test_task_cache_is_checked_after_permissions(client, make_user, task_cache_setup, fake_redis):
    s = task_cache_setup
    stranger = make_user("stranger")
    client.get(s.url(), headers=s.owner["headers"])  # đã có trong cache

    assert client.get(s.url()).status_code == 401
    assert client.get(s.url(), headers=stranger["headers"]).status_code == 404


def test_project_tasks_work_without_redis(client, task_cache_setup):
    s = task_cache_setup

    responses = [client.get(s.url(), headers=s.owner["headers"]) for _ in range(2)]

    assert [r.status_code for r in responses] == [200, 200]
    assert [r.headers["X-Cache"] for r in responses] == ["MISS", "MISS"]


def test_task_cache_version_moves_only_on_commit(db, task_cache_setup, fake_redis):
    """Event của Session: flush rồi rollback -> không đổi version; commit -> version + 1."""
    s = task_cache_setup
    project_id = s.project["id"]
    start = task_cache.current_version(project_id)
    task = db.get(Task, s.task["id"])
    assert task is not None

    task.title = "Draft"
    db.flush()  # đã ghi xuống DB nhưng chưa commit
    db.rollback()
    db.commit()  # transaction mới, không đổi gì: không được làm mới vì lần flush đã bị rollback
    after_rollback = task_cache.current_version(project_id)
    task.title = "Final"
    db.commit()

    assert after_rollback == start
    assert task_cache.current_version(project_id) == start + 1


def test_comment_or_activity_on_a_task_keeps_the_task_cache(db, task_cache_setup, fake_redis):
    """Danh sách task không chứa comment / activity: thêm vào thì không cần làm mới cache, kể cả
    khi collection `comments` / `activities` của task đã được load (có history thay đổi)."""
    s = task_cache_setup
    start = task_cache.current_version(s.project["id"])
    task = db.get(Task, s.task["id"])
    owner = db.get(User, s.owner["id"])
    assert task is not None and owner is not None

    task.comments.append(Comment(author=owner, content="LGTM"))
    task.activities.append(TaskActivity(actor=owner, action=ActivityAction.COMMENTED))
    db.commit()

    assert task_cache.current_version(s.project["id"]) == start


def test_deleted_project_task_cache_expires(client, task_cache_setup, fake_redis):
    s = task_cache_setup
    client.get(s.url(), headers=s.owner["headers"])

    client.delete(f"/api/v1/projects/{s.project['id']}", headers=s.owner["headers"])

    # Version key của project đã xóa không nằm mãi trong Redis
    assert fake_redis.ttl(f"taskhub:projects:{s.project['id']}:tasks:version") > 0


def test_task_expired_by_an_earlier_commit_still_refreshes_its_project(
    db, task_cache_setup, fake_redis
):
    """Object đã commit 1 lần (mọi attribute hết hạn) rồi sửa tiếp: vẫn phải biết task thuộc
    project nào, không được làm mới nhầm key `projects:None`."""
    s = task_cache_setup
    start = task_cache.current_version(s.project["id"])
    task = db.get(Task, s.task["id"])
    assert task is not None
    db.commit()  # expire_on_commit: project_id cũng hết hạn

    task.title = "Renamed after commit"
    db.commit()

    assert task_cache.current_version(s.project["id"]) == start + 1
    assert fake_redis.keys("taskhub:projects:None:*") == []


def test_bulk_update_through_the_session_refreshes_the_task_cache(
    db, task_cache_setup, fake_redis
):
    """UPDATE hàng loạt (vd crud.task.touch) không đi qua unit of work: vẫn phải làm mới."""
    s = task_cache_setup
    start = task_cache.current_version(s.project["id"])

    crud.task.touch(db, [s.task["id"]])
    db.commit()

    assert task_cache.current_version(s.project["id"]) == start + 1
    assert task_cache.current_version(s.other_project["id"]) == 0  # project khác không bị đụng


def test_all_versions_are_bumped_in_one_round_trip(
    client, make_task, task_cache_setup, fake_redis, monkeypatch
):
    """Nhiều project cùng đổi (vd user đổi tên) -> 1 pipeline Redis, không phải 1 lệnh / project:
    Redis chết thì chỉ chờ timeout 1 lần."""
    s = task_cache_setup
    make_task(s.project["id"], s.owner, title="Owner task")  # owner có task ở cả 2 project
    project_ids = (s.project["id"], s.other_project["id"])
    before = [task_cache.current_version(pid) for pid in project_ids]
    pipelines = []
    original = fake_redis.pipeline

    def counting_pipeline(*args, **kwargs):
        pipelines.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(fake_redis, "pipeline", counting_pipeline)
    client.patch("/api/v1/users/me", json={"full_name": "Owner 2"}, headers=s.owner["headers"])

    assert len(pipelines) == 1
    assert [task_cache.current_version(pid) for pid in project_ids] == [v + 1 for v in before]


def test_redis_down_waits_for_a_single_timeout(db, task_cache_setup, monkeypatch):
    s = task_cache_setup
    unreachable = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    monkeypatch.setattr(cache, "get_redis", lambda: unreachable)
    calls = []
    original = unreachable.pipeline
    monkeypatch.setattr(
        unreachable, "pipeline", lambda *a, **k: calls.append(1) or original(*a, **k)
    )
    owner = db.get(User, s.owner["id"])
    assert owner is not None
    for project_id in (s.project["id"], s.other_project["id"]):
        task = Task(title=f"T{project_id}", project_id=project_id, creator=owner)
        db.add(task)

    db.commit()  # 2 project đổi, Redis không kết nối được: không lỗi, chỉ 1 lần thử

    assert len(calls) == 1


def test_cache_key_changes_with_the_response_schema():
    """Đổi hình dạng response (thêm field...) -> fingerprint khác -> key khác: bản deploy mới
    không đọc phải dữ liệu cache theo hình dạng cũ."""

    class V1(BaseModel):
        id: int

    class V2(BaseModel):
        id: int
        title: str

    fingerprint = cache.schema_fingerprint(Page[TaskOut])
    key = task_cache.page_key(1, 0, status=None, priority=None, assignee_id=None, page=1, limit=20)

    assert cache.schema_fingerprint(V1) != cache.schema_fingerprint(V2)
    assert cache.schema_fingerprint(Page[TaskOut]) == fingerprint  # ổn định giữa các lần gọi
    assert f":{fingerprint}:" in key


def test_cache_events_are_registered_by_importing_models_only():
    """Script / worker chỉ import model (không import service nào) vẫn có event làm mới cache."""
    code = (
        "import sys, app.models\n"
        "from sqlalchemy import event\n"
        "from sqlalchemy.orm import Session\n"
        "tc = sys.modules['app.services.task_cache']\n"
        "assert 'app.services.tasks' not in sys.modules\n"
        "assert event.contains(Session, 'after_commit', tc._invalidate_after_commit)\n"
    )
    env = {**os.environ, "SECRET_KEY": "x" * 32, "DATABASE_URL": "sqlite://"}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stderr


def test_no_change_tracking_when_redis_is_disabled(client, task_cache_setup, sql_log):
    """Không cấu hình Redis: event không làm gì, đổi tên user không chạy thêm query tìm project."""
    s = task_cache_setup

    client.patch("/api/v1/users/me", json={"full_name": "Dev 2"}, headers=s.dev["headers"])

    assert not any("DISTINCT tasks.project_id" in sql for sql in sql_log)


def test_full_name_cannot_contain_line_breaks(client, make_user):
    alice = make_user("alice")
    bad = "Alice\nBcc: victim@example.com"

    register = client.post(
        "/api/v1/auth/register",
        json={"full_name": bad, "email": "x@example.com", "password": "Password123"},
    )
    update = client.patch("/api/v1/users/me", json={"full_name": bad}, headers=alice["headers"])

    assert (register.status_code, update.status_code) == (422, 422)


def test_email_subject_flattens_names_already_stored_with_line_breaks(sent_emails):
    """Dữ liệu cũ trong DB có thể còn tên xuống dòng: tiêu đề email gộp lại thành 1 dòng."""
    email_service.notify_task_assigned(
        "dev@example.com",
        task_id=1,
        task_title="Login",
        project_name="TaskHub",
        priority="HIGH",
        due_date=None,
        assigner="Alice\nNguyen",
    )

    assert sent_emails[0]["subject"] == "[TaskHub] Alice Nguyen assigned you task #1: Login"
