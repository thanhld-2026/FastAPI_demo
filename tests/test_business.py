"""Mục 6: Nghiệp vụ assign / comment, transaction và phân quyền chặt chẽ."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.crud import activity as activity_crud
from app.models import User


@pytest.fixture
def setup_task(make_user, make_project, make_task):
    """PM tạo project, member `creator` tạo task trong project."""
    pm = make_user("pmuser")
    creator = make_user("creator")
    project = make_project(pm)
    task = make_task(project["id"], creator, title="Build comment API")
    return pm, creator, task


# ---------- Assign ----------
def test_pm_can_assign_task_and_activity_is_logged(client, make_user, setup_task):
    pm, _, task = setup_task
    dev = make_user("dev")

    resp = client.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"assignee_id": dev["id"]}, headers=pm["headers"]
    )
    activities = client.get(f"/api/v1/tasks/{task['id']}/activities").json()["items"]

    assert resp.status_code == 200
    assert resp.json()["assignee"]["username"] == "dev"
    assert [(a["action"], a["detail"]) for a in activities] == [
        ("created", None),
        ("assigned", "assigned to dev"),
    ]
    assert activities[1]["actor"]["username"] == "pmuser"


def test_non_manager_cannot_assign_task(client, make_user, setup_task):
    _, creator, task = setup_task
    dev = make_user("dev")

    # creator là người tạo task nhưng không phải PM của project -> không được assign
    resp = client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": dev["id"]},
        headers=creator["headers"],
    )

    assert resp.status_code == 403



def test_reassigning_same_user_does_not_log_activity(client, make_user, setup_task):
    pm, _, task = setup_task
    dev = make_user("dev")
    url = f"/api/v1/tasks/{task['id']}/assign"

    client.post(url, json={"assignee_id": dev["id"]}, headers=pm["headers"])
    again = client.post(url, json={"assignee_id": dev["id"]}, headers=pm["headers"])
    activities = client.get(f"/api/v1/tasks/{task['id']}/activities").json()["items"]

    assert again.status_code == 200
    assert again.json()["assignee"]["username"] == "dev"
    # Không đổi người nhận -> không ghi thêm activity (giống update khi không có gì thay đổi)
    assert [a["action"] for a in activities] == ["created", "assigned"]

def test_admin_can_assign_and_unassign(client, make_user, setup_task):
    _, creator, task = setup_task
    admin = make_user("boss", admin=True)
    url = f"/api/v1/tasks/{task['id']}/assign"

    assigned = client.post(url, json={"assignee_id": creator["id"]}, headers=admin["headers"])
    unassigned = client.post(url, json={"assignee_id": None}, headers=admin["headers"])

    assert assigned.json()["assignee"]["username"] == "creator"
    assert unassigned.status_code == 200
    assert unassigned.json()["assignee"] is None


def test_assign_to_missing_or_inactive_user_returns_400(client, make_user, setup_task):
    pm, _, task = setup_task
    admin = make_user("boss", admin=True)
    sleeper = make_user("sleeper")
    client.patch(
        f"/api/v1/users/{sleeper['id']}", json={"is_active": False}, headers=admin["headers"]
    )
    url = f"/api/v1/tasks/{task['id']}/assign"

    missing = client.post(url, json={"assignee_id": 999}, headers=pm["headers"])
    inactive = client.post(url, json={"assignee_id": sleeper["id"]}, headers=pm["headers"])

    assert missing.status_code == 400
    assert inactive.status_code == 400
    unknown_task = client.post(
        "/api/v1/tasks/999/assign", json={"assignee_id": None}, headers=pm["headers"]
    )
    assert unknown_task.status_code == 404


def test_assignee_id_must_be_positive(client, setup_task):
    pm, _, task = setup_task

    resp = client.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"assignee_id": 0}, headers=pm["headers"]
    )

    assert resp.status_code == 422


def test_assign_is_rolled_back_when_activity_logging_fails(
    client, make_user, setup_task, monkeypatch
):
    """Transaction: bước 2 (ghi activity) lỗi -> bước 1 (đổi assignee) cũng không được lưu."""
    pm, _, task = setup_task
    dev = make_user("dev")

    def broken_add(*args, **kwargs):
        raise RuntimeError("simulated failure while writing activity")

    monkeypatch.setattr(activity_crud, "add", broken_add)
    resp = client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": dev["id"]},
        headers=pm["headers"],
    )
    monkeypatch.undo()

    assert resp.status_code == 500

    after = client.get(f"/api/v1/tasks/{task['id']}").json()
    activities = client.get(f"/api/v1/tasks/{task['id']}/activities").json()["items"]
    assert after["assignee"] is None
    assert [a["action"] for a in activities] == ["created"]



def test_user_with_activity_history_cannot_be_deleted(client, db, make_user, setup_task):
    """Activity log là dữ liệu audit: actor_id RESTRICT -> không xóa được user còn lịch sử."""
    _, creator, task = setup_task
    admin = make_user("boss", admin=True)  # chỉ dính tới DB qua activity "assigned"
    client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": creator["id"]},
        headers=admin["headers"],
    )

    db.delete(db.get(User, admin["id"]))
    with pytest.raises(IntegrityError):
        db.commit()

# ---------- Comments ----------
def test_logged_in_user_can_comment(client, make_user, setup_task):
    _, _, task = setup_task
    reviewer = make_user("reviewer")
    url = f"/api/v1/tasks/{task['id']}/comments"

    anonymous = client.post(url, json={"content": "Hi"})
    created = client.post(url, json={"content": "  LGTM!  "}, headers=reviewer["headers"])
    listed = client.get(url).json()["items"]

    assert anonymous.status_code == 401
    assert created.status_code == 201
    assert created.json()["content"] == "LGTM!"  # khoảng trắng thừa được cắt
    assert created.json()["author"]["username"] == "reviewer"
    assert [c["content"] for c in listed] == ["LGTM!"]
    activities = client.get(f"/api/v1/tasks/{task['id']}/activities").json()["items"]
    assert activities[-1]["action"] == "commented"


def test_only_author_pm_or_admin_can_modify_comment(client, make_user, setup_task):
    pm, creator, task = setup_task
    author = make_user("author")
    admin = make_user("boss", admin=True)
    base = f"/api/v1/tasks/{task['id']}/comments"
    comment_1 = client.post(base, json={"content": "first"}, headers=author["headers"]).json()
    comment_2 = client.post(base, json={"content": "second"}, headers=author["headers"]).json()

    # creator sở hữu task nhưng KHÔNG phải tác giả comment, cũng không phải PM -> cấm
    forbidden_edit = client.put(
        f"{base}/{comment_1['id']}", json={"content": "x"}, headers=creator["headers"]
    )
    forbidden_delete = client.delete(f"{base}/{comment_1['id']}", headers=creator["headers"])
    author_edit = client.put(
        f"{base}/{comment_1['id']}", json={"content": "edited"}, headers=author["headers"]
    )
    pm_delete = client.delete(f"{base}/{comment_1['id']}", headers=pm["headers"])
    admin_delete = client.delete(f"{base}/{comment_2['id']}", headers=admin["headers"])

    assert forbidden_edit.status_code == 403
    assert forbidden_delete.status_code == 403
    assert author_edit.status_code == 200
    assert author_edit.json()["content"] == "edited"
    assert pm_delete.status_code == 204
    assert admin_delete.status_code == 204
    assert client.get(base).json()["items"] == []


def test_comment_must_belong_to_task_in_url(client, make_user, make_task, setup_task):
    pm, _, task = setup_task
    other_task = make_task(task["project_id"], pm, title="Other task")
    comment = client.post(
        f"/api/v1/tasks/{task['id']}/comments", json={"content": "hello"}, headers=pm["headers"]
    ).json()

    resp = client.delete(
        f"/api/v1/tasks/{other_task['id']}/comments/{comment['id']}", headers=pm["headers"]
    )

    assert resp.status_code == 404
