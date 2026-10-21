"""Mục 3, 5, 7: Task, lọc & phân trang, bookmark, N+1 query.

Test đầu tiên là Integration Test bắt buộc của mục 7: luồng Đăng ký -> Tạo Task.
"""

from datetime import date, timedelta

from sqlalchemy import select, update

from app.models import Task
from tests.conftest import DEFAULT_PASSWORD


def test_register_login_and_create_task_flow(client):
    """Đi qua API giống hệt 1 client thật: không chạm trực tiếp vào DB."""
    # 1. Đăng ký
    register = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": DEFAULT_PASSWORD},
    )
    assert register.status_code == 201

    # 2. Đăng nhập -> nhận access token
    login = client.post(
        "/api/v1/auth/login", data={"username": "alice", "password": DEFAULT_PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 3. Tạo workspace (người tạo là OWNER) rồi tạo project trong workspace
    workspace = client.post("/api/v1/workspaces", json={"name": "Team"}, headers=headers)
    assert workspace.status_code == 201
    project = client.post(
        f"/api/v1/workspaces/{workspace.json()['id']}/projects",
        json={"name": "TaskHub"},
        headers=headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # 4. Tạo task trong project
    due_date = (date.today() + timedelta(days=7)).isoformat()
    created = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Viết API đăng ký", "priority": "HIGH", "due_date": due_date},
        headers=headers,
    )
    assert created.status_code == 201
    task = created.json()
    assert task["title"] == "Viết API đăng ký"
    assert task["status"] == "TODO"  # giá trị mặc định
    assert task["priority"] == "HIGH"
    assert task["due_date"] == due_date
    assert task["creator"]["username"] == "alice"
    assert task["assignee"] is None

    # 5. Đọc lại: task xuất hiện trong danh sách task của project
    listed = client.get(f"/api/v1/projects/{project_id}/tasks", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == task["id"]


def test_create_task_requires_login(client, make_user, make_project):
    project = make_project(make_user("pmuser"))

    resp = client.post(f"/api/v1/projects/{project['id']}/tasks", json={"title": "X"})

    assert resp.status_code == 401


def test_create_task_with_tags(client, make_user, make_project, make_tag):
    pm = make_user("pmuser")
    project = make_project(pm)
    backend, bug = make_tag("backend"), make_tag("bug")

    resp = client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "Fix login", "tag_ids": [bug["id"], backend["id"], bug["id"]]},
        headers=pm["headers"],
    )

    assert resp.status_code == 201
    assert [t["name"] for t in resp.json()["tags"]] == ["backend", "bug"]


def test_create_task_with_unknown_tag_returns_400(client, make_user, make_project):
    pm = make_user("pmuser")
    project = make_project(pm)

    resp = client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "X", "tag_ids": [999]},
        headers=pm["headers"],
    )

    assert resp.status_code == 400


def test_filter_tasks_by_status_and_priority(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    make_task(project["id"], pm, title="A", status="TODO", priority="HIGH")
    make_task(project["id"], pm, title="B", status="TODO", priority="LOW")
    make_task(project["id"], pm, title="C", status="DONE", priority="HIGH")

    resp = client.get(
        "/api/v1/tasks", params={"status": "TODO", "priority": "HIGH"}, headers=pm["headers"]
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert [t["title"] for t in resp.json()["items"]] == ["A"]


def test_filter_with_invalid_enum_returns_422(client, make_user):
    headers = make_user("alice")["headers"]
    resp = client.get("/api/v1/tasks", params={"status": "UNKNOWN"}, headers=headers)
    assert resp.status_code == 422


def test_search_tasks_by_title(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    make_task(project["id"], pm, title="Implement login API")
    make_task(project["id"], pm, title="Design homepage")

    resp = client.get("/api/v1/tasks", params={"q": "LOGIN"}, headers=pm["headers"])

    assert [t["title"] for t in resp.json()["items"]] == ["Implement login API"]


def test_paginate_project_tasks(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    for i in range(15):
        make_task(project["id"], pm, title=f"Task {i:02d}")

    resp = client.get(
        f"/api/v1/projects/{project['id']}/tasks",
        params={"page": 3, "limit": 5},
        headers=pm["headers"],
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 15
    assert (body["page"], body["limit"], body["pages"]) == (3, 5, 3)
    # Sắp xếp mới nhất trước: trang 3 (bỏ qua 10 task) chứa 5 task được tạo sớm nhất
    assert [t["title"] for t in body["items"]] == [f"Task {i:02d}" for i in range(4, -1, -1)]


def test_pagination_params_are_validated(client, make_user):
    headers = make_user("alice")["headers"]

    def status_of(params: dict) -> int:
        return client.get("/api/v1/tasks", params=params, headers=headers).status_code

    assert status_of({"limit": 101}) == 422
    assert status_of({"page": 0}) == 422
    # page quá lớn: trước đây offset tràn kiểu số nguyên của DB -> 500
    assert status_of({"page": 10_001}) == 422
    assert status_of({"page": 10**17}) == 422


def test_old_skip_param_is_rejected(client, make_user):
    headers = make_user("alice")["headers"]
    resp = client.get("/api/v1/tasks", params={"skip": 20, "limit": 20}, headers=headers)

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["query", "skip"]
    assert "use page" in resp.json()["detail"][0]["msg"]


def test_empty_and_out_of_range_pages(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    headers = pm["headers"]
    empty = client.get("/api/v1/tasks", headers=headers).json()
    project = make_project(pm)
    for i in range(3):
        make_task(project["id"], pm, title=f"T{i}")

    last = client.get("/api/v1/tasks", params={"page": 2, "limit": 2}, headers=headers).json()
    beyond = client.get("/api/v1/tasks", params={"page": 5, "limit": 2}, headers=headers)

    assert (empty["total"], empty["page"], empty["pages"]) == (0, 1, 1)  # không phải "1/0"
    assert (len(last["items"]), last["pages"]) == (1, 2)
    assert beyond.status_code == 200
    assert (beyond.json()["items"], beyond.json()["pages"]) == ([], 2)


def test_filter_ids_must_be_positive(client, make_user):
    headers = make_user("alice")["headers"]
    assert client.get("/api/v1/tasks", params={"project_id": 0}, headers=headers).status_code == 422
    assert (
        client.get("/api/v1/tasks", params={"assignee_id": -1}, headers=headers).status_code
        == 422
    )


def test_bookmark_requires_login(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)

    resp = client.post(f"/api/v1/tasks/{task['id']}/bookmark")

    assert resp.status_code == 401


def test_bookmark_and_unbookmark(client, make_user, make_project, make_task, add_member):
    pm = make_user("pmuser")
    reader = make_user("reader")
    project = make_project(pm)
    add_member(project, pm, reader, role="VIEWER")  # bookmark là dữ liệu cá nhân, VIEWER cũng được
    task = make_task(project["id"], pm, title="Interesting task")
    url = f"/api/v1/tasks/{task['id']}/bookmark"

    first = client.post(url, headers=reader["headers"])
    again = client.post(url, headers=reader["headers"])  # idempotent, không lỗi
    bookmarks = client.get("/api/v1/users/me/bookmarks", headers=reader["headers"]).json()
    removed = client.delete(url, headers=reader["headers"])
    after = client.get("/api/v1/users/me/bookmarks", headers=reader["headers"]).json()

    assert first.json() == {"task_id": task["id"], "bookmarked": True}
    assert again.status_code == 200
    assert bookmarks["total"] == 1
    assert [t["title"] for t in bookmarks["items"]] == ["Interesting task"]
    assert removed.json()["bookmarked"] is False
    assert (after["total"], after["items"]) == (0, [])
    assert client.post("/api/v1/tasks/999/bookmark", headers=reader["headers"]).status_code == 404


def test_task_edit_and_delete_permissions(
    client, make_user, make_project, make_task, add_member
):
    owner = make_user("owner")
    creator = make_user("creator")
    other_editor = make_user("other")
    viewer = make_user("viewer")
    stranger = make_user("stranger")
    project = make_project(owner)
    add_member(project, owner, creator)
    add_member(project, owner, other_editor)
    add_member(project, owner, viewer, role="VIEWER")
    task = make_task(project["id"], creator)
    second = make_task(project["id"], creator, title="Second")
    url = f"/api/v1/tasks/{task['id']}"
    body = {"status": "IN_PROGRESS"}

    # Sửa: mọi EDITOR; VIEWER bị cấm; người ngoài không thấy task (404)
    assert client.put(url, json=body, headers=stranger["headers"]).status_code == 404
    assert client.put(url, json=body, headers=viewer["headers"]).status_code == 403
    updated = client.put(url, json=body, headers=other_editor["headers"])
    assert updated.status_code == 200
    assert updated.json()["status"] == "IN_PROGRESS"

    # Xóa: EDITOR chỉ xóa task mình tạo, OWNER xóa được mọi task
    assert client.delete(url, headers=other_editor["headers"]).status_code == 403
    assert client.delete(url, headers=creator["headers"]).status_code == 204
    by_owner = client.delete(f"/api/v1/tasks/{second['id']}", headers=owner["headers"])
    assert by_owner.status_code == 204


def test_update_task_rejects_null_for_required_fields(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)

    resp = client.put(f"/api/v1/tasks/{task['id']}", json={"title": None}, headers=pm["headers"])

    assert resp.status_code == 422


def test_unbookmark_is_idempotent(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)

    resp = client.delete(f"/api/v1/tasks/{task['id']}/bookmark", headers=pm["headers"])

    # Task chưa từng được bookmark: vẫn 200, trạng thái cuối cùng là "không bookmark"
    assert resp.status_code == 200
    assert resp.json() == {"task_id": task["id"], "bookmarked": False}


def test_due_date_cannot_be_in_the_past(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    task = make_task(project["id"], pm)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    created = client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "X", "due_date": yesterday},
        headers=pm["headers"],
    )
    updated = client.put(
        f"/api/v1/tasks/{task['id']}", json={"due_date": yesterday}, headers=pm["headers"]
    )

    assert created.status_code == 422
    assert updated.status_code == 422


def test_overdue_task_can_still_be_updated(client, db, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)
    # API không cho đặt ngày quá khứ -> sửa thẳng trong DB để có 1 task đã quá hạn
    overdue = date.today() - timedelta(days=3)
    db.execute(update(Task).where(Task.id == task["id"]).values(due_date=overdue))
    db.commit()

    resp = client.put(f"/api/v1/tasks/{task['id']}", json={"status": "DONE"}, headers=pm["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "DONE"
    assert resp.json()["due_date"] == overdue.isoformat()


def test_error_responses_are_documented(client):
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/api/v1/tasks/{task_id}"]["put"]["responses"]

    assert {"400", "401", "403", "404", "422"} <= responses.keys()
    schema = responses["404"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/ErrorResponse")



def test_title_must_be_single_line(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    task = make_task(project["id"], pm)

    created = client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "Fix\nlogin"},
        headers=pm["headers"],
    )
    updated = client.put(
        f"/api/v1/tasks/{task['id']}", json={"title": "Fix\r\nlogin"}, headers=pm["headers"]
    )

    assert created.status_code == 422
    assert updated.status_code == 422


def test_in_review_status_and_urgent_priority(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    make_task(project["id"], pm, title="Review PR", status="IN_REVIEW", priority="URGENT")
    make_task(project["id"], pm, title="Other task")

    resp = client.get(
        "/api/v1/tasks", params={"status": "IN_REVIEW", "priority": "URGENT"}, headers=pm["headers"]
    )

    assert [t["title"] for t in resp.json()["items"]] == ["Review PR"]

# ---------- N+1 query ----------
def _seed_tasks(client, make_user, make_project, make_task, make_tag, add_member, count: int):
    pm = make_user(f"pm_{count}")
    dev = make_user(f"dev_{count}")
    tag = make_tag(f"tag-{count}")
    project = make_project(pm)
    add_member(project, pm, dev)
    for i in range(count):
        task = make_task(project["id"], pm, title=f"T{i}", tag_ids=[tag["id"]])
        client.post(
            f"/api/v1/tasks/{task['id']}/assign",
            json={"assignee_id": dev["id"]},
            headers=pm["headers"],
        )


def test_listing_tasks_runs_constant_number_of_queries(
    client, make_user, make_project, make_task, make_tag, add_member, sql_log
):
    """Số query KHÔNG tăng theo số task nhờ joinedload / selectinload."""
    admin = make_user("boss", admin=True)  # admin thấy task ở mọi workspace
    seed = (client, make_user, make_project, make_task, make_tag, add_member)
    _seed_tasks(*seed, count=2)
    sql_log.clear()
    client.get("/api/v1/tasks", headers=admin["headers"])
    queries_for_2_tasks = len(sql_log)

    _seed_tasks(*seed, count=10)
    sql_log.clear()
    resp = client.get("/api/v1/tasks", headers=admin["headers"])
    queries_for_12_tasks = len(sql_log)

    assert resp.json()["total"] == 12
    # 1 SELECT user (xác thực token) + 1 COUNT + 1 SELECT tasks JOIN users
    # + 1 SELECT tags WHERE task_id IN (...)
    assert queries_for_2_tasks == queries_for_12_tasks == 4


def test_lazy_loading_causes_n_plus_one(
    client, db, make_user, make_project, make_task, make_tag, add_member, sql_log
):
    """Minh họa vấn đề: KHÔNG eager load thì mỗi task sinh thêm query riêng."""
    _seed_tasks(client, make_user, make_project, make_task, make_tag, add_member, count=5)
    sql_log.clear()

    tasks = db.scalars(select(Task)).all()  # 1 query
    for task in tasks:
        _ = task.assignee.username  # lazy load: +1 query / task (lần đầu gặp user đó)
        _ = [tag.name for tag in task.tags]  # lazy load: +1 query / task

    assert len(sql_log) > len(tasks)  # 1 + N... -> chính là N+1
