"""Mục 6 + phụ lục 11: nghiệp vụ assign / comment, transaction, phân quyền theo role."""

from dataclasses import dataclass

import pytest
from sqlalchemy.exc import IntegrityError

from app.crud import activity as activity_crud
from app.models import User


@dataclass
class Setup:
    owner: dict
    editor: dict  # tạo task
    viewer: dict
    project: dict
    task: dict


@pytest.fixture
def setup(make_user, make_project, make_task, add_member) -> Setup:
    """OWNER tạo project; EDITOR `creator` tạo task; thêm 1 VIEWER."""
    owner = make_user("owner")
    editor = make_user("creator")
    viewer = make_user("viewer")
    project = make_project(owner)
    add_member(project, owner, editor, role="EDITOR")
    add_member(project, owner, viewer, role="VIEWER")
    task = make_task(project["id"], editor, title="Build comment API")
    return Setup(owner, editor, viewer, project, task)


def _activities(client, task: dict, user: dict) -> list[dict]:
    resp = client.get(f"/api/v1/tasks/{task['id']}/activities", headers=user["headers"])
    return resp.json()["items"]


# ---------- Assign ----------
def test_editor_can_assign_task_and_activity_is_logged(client, make_user, add_member, setup):
    dev = make_user("dev")
    add_member(setup.project, setup.owner, dev)

    resp = client.post(
        f"/api/v1/tasks/{setup.task['id']}/assign",
        json={"assignee_id": dev["id"]},
        headers=setup.editor["headers"],
    )
    activities = _activities(client, setup.task, setup.owner)

    assert resp.status_code == 200
    assert resp.json()["assignee"]["username"] == "dev"
    assert [(a["action"], a["detail"]) for a in activities] == [
        ("created", None),
        ("assigned", "assigned to dev"),
    ]
    assert activities[1]["actor"]["username"] == "creator"


def test_viewer_cannot_assign_task(client, setup):
    resp = client.post(
        f"/api/v1/tasks/{setup.task['id']}/assign",
        json={"assignee_id": setup.editor["id"]},
        headers=setup.viewer["headers"],
    )

    assert resp.status_code == 403


def test_assignee_must_be_an_editor_of_the_workspace(client, make_user, setup):
    outsider = make_user("outsider")
    admin = make_user("boss", admin=True)
    sleeper = make_user("sleeper")
    url = f"/api/v1/tasks/{setup.task['id']}/assign"
    headers = setup.owner["headers"]

    to_viewer = client.post(url, json={"assignee_id": setup.viewer["id"]}, headers=headers)
    to_outsider = client.post(url, json={"assignee_id": outsider["id"]}, headers=headers)
    to_missing = client.post(url, json={"assignee_id": 999}, headers=headers)
    client.patch(
        f"/api/v1/users/{sleeper['id']}", json={"is_active": False}, headers=admin["headers"]
    )
    to_inactive = client.post(url, json={"assignee_id": sleeper["id"]}, headers=headers)
    unknown_task = client.post(
        "/api/v1/tasks/999/assign", json={"assignee_id": None}, headers=headers
    )

    assert [r.status_code for r in (to_viewer, to_outsider, to_missing, to_inactive)] == [400] * 4
    assert unknown_task.status_code == 404


def test_reassigning_same_user_does_not_log_activity(client, setup):
    url = f"/api/v1/tasks/{setup.task['id']}/assign"
    headers = setup.owner["headers"]

    client.post(url, json={"assignee_id": setup.editor["id"]}, headers=headers)
    again = client.post(url, json={"assignee_id": setup.editor["id"]}, headers=headers)
    activities = _activities(client, setup.task, setup.owner)

    assert again.status_code == 200
    assert again.json()["assignee"]["username"] == "creator"
    # Không đổi người nhận -> không ghi thêm activity (giống update khi không có gì thay đổi)
    assert [a["action"] for a in activities] == ["created", "assigned"]


def test_admin_can_assign_and_unassign_without_membership(client, make_user, setup):
    admin = make_user("boss", admin=True)
    url = f"/api/v1/tasks/{setup.task['id']}/assign"

    assigned = client.post(url, json={"assignee_id": setup.editor["id"]}, headers=admin["headers"])
    unassigned = client.post(url, json={"assignee_id": None}, headers=admin["headers"])

    assert assigned.json()["assignee"]["username"] == "creator"
    assert unassigned.status_code == 200
    assert unassigned.json()["assignee"] is None


def test_assignee_id_must_be_positive(client, setup):
    resp = client.post(
        f"/api/v1/tasks/{setup.task['id']}/assign",
        json={"assignee_id": 0},
        headers=setup.owner["headers"],
    )

    assert resp.status_code == 422


def test_assign_is_rolled_back_when_activity_logging_fails(client, setup, monkeypatch):
    """Transaction: bước 2 (ghi activity) lỗi -> bước 1 (đổi assignee) cũng không được lưu."""

    def broken_add(*args, **kwargs):
        raise RuntimeError("simulated failure while writing activity")

    monkeypatch.setattr(activity_crud, "add", broken_add)
    resp = client.post(
        f"/api/v1/tasks/{setup.task['id']}/assign",
        json={"assignee_id": setup.editor["id"]},
        headers=setup.owner["headers"],
    )
    monkeypatch.undo()

    assert resp.status_code == 500
    after = client.get(f"/api/v1/tasks/{setup.task['id']}", headers=setup.owner["headers"])
    assert after.json()["assignee"] is None
    assert [a["action"] for a in _activities(client, setup.task, setup.owner)] == ["created"]


def test_user_with_activity_history_cannot_be_deleted(client, db, make_user, setup):
    """Activity log là dữ liệu audit: actor_id RESTRICT -> không xóa được user còn lịch sử."""
    admin = make_user("boss", admin=True)  # chỉ dính tới DB qua activity "assigned"
    client.post(
        f"/api/v1/tasks/{setup.task['id']}/assign",
        json={"assignee_id": setup.editor["id"]},
        headers=admin["headers"],
    )

    db.delete(db.get(User, admin["id"]))
    with pytest.raises(IntegrityError):
        db.commit()


# ---------- Comments ----------
def test_editor_can_comment_viewer_cannot(client, make_user, setup):
    url = f"/api/v1/tasks/{setup.task['id']}/comments"
    stranger = make_user("stranger")

    anonymous = client.post(url, json={"content": "Hi"})
    by_stranger = client.post(url, json={"content": "Hi"}, headers=stranger["headers"])
    by_viewer = client.post(url, json={"content": "Hi"}, headers=setup.viewer["headers"])
    created = client.post(url, json={"content": "  LGTM!  "}, headers=setup.editor["headers"])
    listed = client.get(url, headers=setup.viewer["headers"]).json()["items"]

    assert (anonymous.status_code, by_stranger.status_code, by_viewer.status_code) == (
        401,
        404,
        403,
    )
    assert created.status_code == 201
    assert created.json()["content"] == "LGTM!"  # khoảng trắng thừa được cắt
    assert created.json()["author"]["username"] == "creator"
    assert [c["content"] for c in listed] == ["LGTM!"]
    assert _activities(client, setup.task, setup.owner)[-1]["action"] == "commented"


def test_only_author_owner_or_admin_can_modify_comment(client, make_user, add_member, setup):
    author = make_user("author")
    add_member(setup.project, setup.owner, author)
    admin = make_user("boss", admin=True)
    base = f"/api/v1/tasks/{setup.task['id']}/comments"
    comment_1 = client.post(base, json={"content": "first"}, headers=author["headers"]).json()
    comment_2 = client.post(base, json={"content": "second"}, headers=author["headers"]).json()

    # editor (người tạo task) KHÔNG phải tác giả comment, cũng không phải OWNER -> cấm
    forbidden_edit = client.put(
        f"{base}/{comment_1['id']}", json={"content": "x"}, headers=setup.editor["headers"]
    )
    forbidden_delete = client.delete(f"{base}/{comment_1['id']}", headers=setup.editor["headers"])
    author_edit = client.put(
        f"{base}/{comment_1['id']}", json={"content": "edited"}, headers=author["headers"]
    )
    owner_delete = client.delete(f"{base}/{comment_1['id']}", headers=setup.owner["headers"])
    admin_delete = client.delete(f"{base}/{comment_2['id']}", headers=admin["headers"])

    assert forbidden_edit.status_code == 403
    assert forbidden_delete.status_code == 403
    assert author_edit.status_code == 200
    assert author_edit.json()["content"] == "edited"
    assert owner_delete.status_code == 204
    assert admin_delete.status_code == 204
    assert client.get(base, headers=setup.owner["headers"]).json()["items"] == []


def test_author_downgraded_to_viewer_cannot_edit_own_comment(client, setup):
    base = f"/api/v1/tasks/{setup.task['id']}/comments"
    comment = client.post(base, json={"content": "mine"}, headers=setup.editor["headers"]).json()
    client.patch(
        f"/api/v1/workspaces/{setup.project['workspace_id']}/members/{setup.editor['id']}",
        json={"role": "VIEWER"},
        headers=setup.owner["headers"],
    )

    resp = client.put(
        f"{base}/{comment['id']}", json={"content": "x"}, headers=setup.editor["headers"]
    )

    assert resp.status_code == 403


def test_comment_must_belong_to_task_in_url(client, make_task, setup):
    other_task = make_task(setup.project["id"], setup.owner, title="Other task")
    comment = client.post(
        f"/api/v1/tasks/{setup.task['id']}/comments",
        json={"content": "hello"},
        headers=setup.owner["headers"],
    ).json()

    resp = client.delete(
        f"/api/v1/tasks/{other_task['id']}/comments/{comment['id']}",
        headers=setup.owner["headers"],
    )

    assert resp.status_code == 404
