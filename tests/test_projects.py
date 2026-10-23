"""Mục 2, 3, 5: CRUD project, nested response, phân quyền PM."""

import pytest

from app.core.exceptions import ConflictException
from app.dependencies import _raise_if_not_writable
from app.models import ProjectStatus


def test_create_project_requires_login(client):
    resp = client.post("/api/v1/projects", json={"name": "TaskHub"})
    assert resp.status_code == 401


def test_create_and_get_project(client, make_user):
    pm = make_user("pmuser")

    created = client.post(
        "/api/v1/projects",
        json={"name": "TaskHub", "description": "Backend API"},
        headers=pm["headers"],
    )
    project_id = created.json()["id"]
    detail = client.get(f"/api/v1/projects/{project_id}")

    assert created.status_code == 201
    assert created.json()["owner"]["username"] == "pmuser"  # người tạo = PM
    assert detail.status_code == 200
    assert detail.json()["name"] == "TaskHub"
    assert detail.json()["tasks"] == []


def test_get_unknown_project_returns_404(client):
    assert client.get("/api/v1/projects/999").status_code == 404
    assert client.get("/api/v1/projects/999/tasks").status_code == 404


def test_list_projects_is_paginated(client, make_user, make_project):
    pm = make_user("pmuser")
    for i in range(3):
        make_project(pm, name=f"Project {i}")

    resp = client.get("/api/v1/projects", params={"page": 2, "limit": 1})

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert [p["name"] for p in body["items"]] == ["Project 1"]
    assert body["items"][0]["owner"]["username"] == "pmuser"


def test_project_detail_contains_nested_tasks_with_assignee(
    client, make_user, make_project, make_task
):
    pm = make_user("pmuser")
    dev = make_user("dev")
    project = make_project(pm)
    task = make_task(project["id"], pm, title="Design DB")
    client.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"assignee_id": dev["id"]}, headers=pm["headers"]
    )

    detail = client.get(f"/api/v1/projects/{project['id']}").json()

    assert detail["owner"]["username"] == "pmuser"
    assert detail["tasks"][0]["title"] == "Design DB"
    assert detail["tasks"][0]["assignee"]["username"] == "dev"


def test_only_project_manager_or_admin_can_update_project(client, make_user, make_project):
    pm = make_user("pmuser")
    other = make_user("other")
    admin = make_user("boss", admin=True)
    project = make_project(pm)
    url = f"/api/v1/projects/{project['id']}"

    by_other = client.put(url, json={"name": "Hacked"}, headers=other["headers"])
    by_pm = client.put(url, json={"name": "Renamed by PM"}, headers=pm["headers"])
    by_admin = client.put(url, json={"description": "Edited by admin"}, headers=admin["headers"])

    assert by_other.status_code == 403
    assert by_pm.status_code == 200
    assert by_pm.json()["name"] == "Renamed by PM"
    assert by_admin.status_code == 200
    assert by_admin.json()["name"] == "Renamed by PM"  # partial update giữ nguyên field không gửi


def test_delete_project_cascades_to_tasks(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    task = make_task(project["id"], pm)

    resp = client.delete(f"/api/v1/projects/{project['id']}", headers=pm["headers"])

    assert resp.status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404


def test_user_profile_contains_projects_and_assigned_tasks(
    client, make_user, make_project, make_task
):
    pm = make_user("pmuser")
    dev = make_user("dev")
    project = make_project(pm, name="Mobile App")
    task = make_task(project["id"], pm, title="Login screen")
    client.post(
        f"/api/v1/tasks/{task['id']}/assign", json={"assignee_id": dev["id"]}, headers=pm["headers"]
    )

    pm_profile = client.get("/api/v1/users/pmuser/profile").json()
    dev_profile = client.get("/api/v1/users/dev/profile").json()

    assert [p["name"] for p in pm_profile["owned_projects"]] == ["Mobile App"]
    assert pm_profile["owned_projects"][0]["status"] == "ACTIVE"  # FE biết project đã archive chưa
    assert [t["title"] for t in dev_profile["assigned_tasks"]] == ["Login screen"]
    assert "email" not in dev_profile  # profile công khai không lộ email
    assert client.get("/api/v1/users/ghost/profile").status_code == 404


def test_archived_project_is_read_only(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    other = make_user("other")
    dev = make_user("dev")
    project = make_project(pm)
    task = make_task(project["id"], pm)
    url = f"/api/v1/projects/{project['id']}"
    task_url = f"/api/v1/tasks/{task['id']}"
    comment = client.post(
        f"{task_url}/comments", json={"content": "before archive"}, headers=pm["headers"]
    ).json()
    comment_url = f"{task_url}/comments/{comment['id']}"

    forbidden = client.post(f"{url}/archive", headers=other["headers"])
    archived = client.post(f"{url}/archive", headers=pm["headers"])
    again = client.post(f"{url}/archive", headers=pm["headers"])  # idempotent

    assert forbidden.status_code == 403
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert again.status_code == 200
    # Mọi thao tác ghi lên task / comment trong project đã archive -> 409
    writes = [
        client.post(f"{url}/tasks", json={"title": "X"}, headers=pm["headers"]),
        client.put(task_url, json={"status": "DONE"}, headers=pm["headers"]),
        client.post(f"{task_url}/assign", json={"assignee_id": dev["id"]}, headers=pm["headers"]),
        client.post(f"{task_url}/comments", json={"content": "hi"}, headers=pm["headers"]),
        client.put(comment_url, json={"content": "edited"}, headers=pm["headers"]),
        client.delete(comment_url, headers=pm["headers"]),
        client.delete(task_url, headers=pm["headers"]),
    ]
    assert [r.status_code for r in writes] == [409] * len(writes)
    # Đọc vẫn bình thường
    assert client.get(f"{url}/tasks").status_code == 200
    assert client.get(task_url).status_code == 200


def test_unarchive_project_allows_writes_again(client, make_user, make_project):
    pm = make_user("pmuser")
    project = make_project(pm)
    url = f"/api/v1/projects/{project['id']}"
    client.post(f"{url}/archive", headers=pm["headers"])

    reopened = client.post(f"{url}/unarchive", headers=pm["headers"])
    created = client.post(f"{url}/tasks", json={"title": "Back to work"}, headers=pm["headers"])
    renamed = client.put(url, json={"name": "Renamed"}, headers=pm["headers"])

    assert reopened.json()["status"] == "ACTIVE"
    assert created.status_code == 201
    assert renamed.status_code == 200


def test_archived_project_itself_cannot_be_changed_or_deleted(
    client, make_user, make_project, make_task
):
    pm = make_user("pmuser")
    project = make_project(pm)
    task = make_task(project["id"], pm)
    url = f"/api/v1/projects/{project['id']}"
    client.post(f"{url}/archive", headers=pm["headers"])

    renamed = client.put(url, json={"name": "Renamed"}, headers=pm["headers"])
    deleted = client.delete(url, headers=pm["headers"])

    assert renamed.status_code == 409
    assert deleted.status_code == 409
    assert client.get(url).json()["name"] == "TaskHub"
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200  # task không bị xóa theo


# Mọi endpoint ghi: (method, path, body, mã cho người không có quyền khi project ARCHIVED / ACTIVE).
# Tạo task / thêm comment thì user nào đăng nhập cũng được, nên lúc ACTIVE là 201.
WRITE_ENDPOINTS = [
    pytest.param("PUT", "/tasks/{task}", {"status": "DONE"}, 409, 403, id="update-task"),
    pytest.param("DELETE", "/tasks/{task}", None, 409, 403, id="delete-task"),
    pytest.param("POST", "/tasks/{task}/assign", {"assignee_id": None}, 409, 403, id="assign"),
    pytest.param("POST", "/tasks/{task}/comments", {"content": "hi"}, 409, 201, id="add-comment"),
    pytest.param(
        "PUT", "/tasks/{task}/comments/{comment}", {"content": "x"}, 409, 403, id="edit-comment"
    ),
    pytest.param("DELETE", "/tasks/{task}/comments/{comment}", None, 409, 403, id="delete-comment"),
    pytest.param("POST", "/projects/{project}/tasks", {"title": "X"}, 409, 201, id="create-task"),
    pytest.param("PUT", "/projects/{project}", {"name": "X"}, 409, 403, id="update-project"),
    pytest.param("DELETE", "/projects/{project}", None, 409, 403, id="delete-project"),
    # archive / unarchive chạy được ở mọi status nên không có 409
    pytest.param("POST", "/projects/{project}/archive", None, 403, 403, id="archive"),
    pytest.param("POST", "/projects/{project}/unarchive", None, 403, 403, id="unarchive"),
]


@pytest.mark.parametrize(("method", "path", "body", "on_archived", "on_active"), WRITE_ENDPOINTS)
def test_error_order_of_write_endpoints(
    client, make_user, make_project, make_task, method, path, body, on_archived, on_active
):
    """401 (chưa đăng nhập) -> 404 (không có resource) -> 409 (project archive) -> 403 (quyền)."""
    pm = make_user("pmuser")
    stranger = make_user("stranger")  # không phải PM, không tạo task / comment nào
    project = make_project(pm)
    task = make_task(project["id"], pm)
    comment = client.post(
        f"/api/v1/tasks/{task['id']}/comments", json={"content": "by pm"}, headers=pm["headers"]
    ).json()
    url = "/api/v1" + path.format(project=project["id"], task=task["id"], comment=comment["id"])
    missing_url = "/api/v1" + path.format(project=999, task=999, comment=999)
    project_url = f"/api/v1/projects/{project['id']}"

    def call(target: str, user: dict | None = None):
        headers = user["headers"] if user else {}
        return client.request(method, target, json=body, headers=headers)

    anonymous = call(url)
    missing = call(missing_url, stranger)
    client.post(f"{project_url}/archive", headers=pm["headers"])
    archived = call(url, stranger)
    client.post(f"{project_url}/unarchive", headers=pm["headers"])
    active = call(url, stranger)

    codes = [r.status_code for r in (anonymous, missing, archived, active)]
    assert codes == [401, 404, on_archived, on_active]


def test_only_active_projects_accept_writes():
    """Allow-list: chỉ ACTIVE ghi được. Status thêm sau này (vd "ON_HOLD") mặc định là chỉ đọc,
    không vô tình thành ghi được như khi chỉ chặn đúng ARCHIVED."""
    _raise_if_not_writable(ProjectStatus.ACTIVE, "not found")  # không lỗi
    for status in (ProjectStatus.ARCHIVED, "ON_HOLD"):
        with pytest.raises(ConflictException):
            _raise_if_not_writable(status, "not found")  # type: ignore[arg-type]


def test_bookmark_and_admin_tag_delete_still_work_on_archived_project(
    client, make_user, make_project, make_task, make_tag
):
    """2 ngoại lệ có chủ đích của quy tắc archive (xem dependencies.py): bookmark là dữ liệu cá
    nhân; tag dùng chung toàn hệ thống nên admin vẫn xóa được, task archive mất tag đó."""
    pm = make_user("pmuser")
    admin = make_user("boss", admin=True)
    tag = make_tag("legacy")
    project = make_project(pm)
    task = make_task(project["id"], pm, tag_ids=[tag["id"]])
    task_url = f"/api/v1/tasks/{task['id']}"
    client.post(f"/api/v1/projects/{project['id']}/archive", headers=pm["headers"])

    bookmarked = client.post(f"{task_url}/bookmark", headers=pm["headers"])
    unbookmarked = client.delete(f"{task_url}/bookmark", headers=pm["headers"])
    tag_deleted = client.delete(f"/api/v1/tags/{tag['id']}", headers=admin["headers"])

    codes = (bookmarked.status_code, unbookmarked.status_code, tag_deleted.status_code)
    assert codes == (200, 200, 204)
    assert client.get(task_url).json()["tags"] == []


def test_filter_projects_by_status(client, make_user, make_project):
    pm = make_user("pmuser")
    make_project(pm, name="Active one")
    old = make_project(pm, name="Old one")
    client.post(f"/api/v1/projects/{old['id']}/archive", headers=pm["headers"])

    active = client.get("/api/v1/projects", params={"status": "ACTIVE"}).json()
    archived = client.get("/api/v1/projects", params={"status": "ARCHIVED"}).json()

    assert [p["name"] for p in active["items"]] == ["Active one"]
    assert [p["name"] for p in archived["items"]] == ["Old one"]
    assert client.get("/api/v1/projects", params={"status": "DELETED"}).status_code == 422


def test_missing_comment_on_archived_project_is_404(client, make_user, make_project, make_task):
    """Thứ tự lỗi 404 -> 409: comment không tồn tại thì báo 404 kể cả khi project đã archive."""
    pm = make_user("pmuser")
    project = make_project(pm)
    task = make_task(project["id"], pm)
    client.post(f"/api/v1/projects/{project['id']}/archive", headers=pm["headers"])

    resp = client.put(
        f"/api/v1/tasks/{task['id']}/comments/999", json={"content": "x"}, headers=pm["headers"]
    )

    assert resp.status_code == 404
