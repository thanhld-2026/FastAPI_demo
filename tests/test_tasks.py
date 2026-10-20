"""Mục 3, 5: Task, lọc & phân trang, bookmark, phân quyền sửa/xóa task."""

from datetime import date, timedelta

from sqlalchemy import update

from app.models import Task


def test_create_task_requires_login(client, make_user, make_project):
    project = make_project(make_user("pmuser"))

    resp = client.post(f"/api/projects/{project['id']}/tasks", json={"title": "X"})

    assert resp.status_code == 401


def test_create_task_with_tags(client, make_user, make_project, make_tag):
    pm = make_user("pmuser")
    project = make_project(pm)
    backend, bug = make_tag("backend"), make_tag("bug")

    resp = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "Fix login", "tag_ids": [bug["id"], backend["id"], bug["id"]]},
        headers=pm["headers"],
    )

    assert resp.status_code == 201
    assert [t["name"] for t in resp.json()["tags"]] == ["backend", "bug"]


def test_create_task_with_unknown_tag_returns_400(client, make_user, make_project):
    pm = make_user("pmuser")
    project = make_project(pm)

    resp = client.post(
        f"/api/projects/{project['id']}/tasks",
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

    resp = client.get("/api/tasks", params={"status": "TODO", "priority": "HIGH"})

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert [t["title"] for t in resp.json()["items"]] == ["A"]


def test_filter_with_invalid_enum_returns_422(client):
    assert client.get("/api/tasks", params={"status": "UNKNOWN"}).status_code == 422


def test_search_tasks_by_title(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    make_task(project["id"], pm, title="Implement login API")
    make_task(project["id"], pm, title="Design homepage")

    resp = client.get("/api/tasks", params={"q": "LOGIN"})

    assert [t["title"] for t in resp.json()["items"]] == ["Implement login API"]


def test_paginate_project_tasks(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    for i in range(15):
        make_task(project["id"], pm, title=f"Task {i:02d}")

    resp = client.get(f"/api/projects/{project['id']}/tasks", params={"skip": 10, "limit": 5})

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 15
    assert (body["skip"], body["limit"]) == (10, 5)
    # Sắp xếp mới nhất trước: trang 3 (skip=10) chứa 5 task được tạo sớm nhất
    assert [t["title"] for t in body["items"]] == [f"Task {i:02d}" for i in range(4, -1, -1)]


def test_pagination_params_are_validated(client):
    assert client.get("/api/tasks", params={"limit": 101}).status_code == 422
    assert client.get("/api/tasks", params={"skip": -1}).status_code == 422


def test_filter_ids_must_be_positive(client):
    assert client.get("/api/tasks", params={"project_id": 0}).status_code == 422
    assert client.get("/api/tasks", params={"assignee_id": -1}).status_code == 422


def test_bookmark_requires_login(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)

    resp = client.post(f"/api/tasks/{task['id']}/bookmark")

    assert resp.status_code == 401


def test_bookmark_and_unbookmark(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    reader = make_user("reader")
    task = make_task(make_project(pm)["id"], pm, title="Interesting task")
    url = f"/api/tasks/{task['id']}/bookmark"

    first = client.post(url, headers=reader["headers"])
    again = client.post(url, headers=reader["headers"])  # idempotent, không lỗi
    bookmarks = client.get("/api/users/me/bookmarks", headers=reader["headers"]).json()
    removed = client.delete(url, headers=reader["headers"])
    after = client.get("/api/users/me/bookmarks", headers=reader["headers"]).json()

    assert first.json() == {"task_id": task["id"], "bookmarked": True}
    assert again.status_code == 200
    assert bookmarks["total"] == 1
    assert [t["title"] for t in bookmarks["items"]] == ["Interesting task"]
    assert removed.json()["bookmarked"] is False
    assert (after["total"], after["items"]) == (0, [])
    assert client.post("/api/tasks/999/bookmark", headers=reader["headers"]).status_code == 404


def test_task_edit_and_delete_permissions(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    creator = make_user("creator")
    stranger = make_user("stranger")
    task = make_task(make_project(pm)["id"], creator)
    url = f"/api/tasks/{task['id']}"

    assert client.put(url, json={"status": "DONE"}, headers=stranger["headers"]).status_code == 403
    updated = client.put(url, json={"status": "IN_PROGRESS"}, headers=creator["headers"])
    assert updated.status_code == 200
    assert updated.json()["status"] == "IN_PROGRESS"

    assert client.delete(url, headers=stranger["headers"]).status_code == 403
    assert client.delete(url, headers=pm["headers"]).status_code == 204


def test_update_task_rejects_null_for_required_fields(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)

    resp = client.put(f"/api/tasks/{task['id']}", json={"title": None}, headers=pm["headers"])

    assert resp.status_code == 422


def test_unbookmark_is_idempotent(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    task = make_task(make_project(pm)["id"], pm)

    resp = client.delete(f"/api/tasks/{task['id']}/bookmark", headers=pm["headers"])

    # Task chưa từng được bookmark: vẫn 200, trạng thái cuối cùng là "không bookmark"
    assert resp.status_code == 200
    assert resp.json() == {"task_id": task["id"], "bookmarked": False}


def test_due_date_cannot_be_in_the_past(client, make_user, make_project, make_task):
    pm = make_user("pmuser")
    project = make_project(pm)
    task = make_task(project["id"], pm)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    created = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "X", "due_date": yesterday},
        headers=pm["headers"],
    )
    updated = client.put(
        f"/api/tasks/{task['id']}", json={"due_date": yesterday}, headers=pm["headers"]
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

    resp = client.put(f"/api/tasks/{task['id']}", json={"status": "DONE"}, headers=pm["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "DONE"
    assert resp.json()["due_date"] == overdue.isoformat()


def test_error_responses_are_documented(client):
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/api/tasks/{task_id}"]["put"]["responses"]

    assert {"400", "401", "403", "404", "422"} <= responses.keys()
    schema = responses["404"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/ErrorResponse")
