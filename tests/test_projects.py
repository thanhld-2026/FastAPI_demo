"""Mục 2, 3, 5: CRUD project, nested response, phân quyền PM."""


def test_create_project_requires_login(client):
    resp = client.post("/api/projects", json={"name": "TaskHub"})
    assert resp.status_code == 401


def test_create_and_get_project(client, make_user):
    pm = make_user("pmuser")

    created = client.post(
        "/api/projects",
        json={"name": "TaskHub", "description": "Backend API"},
        headers=pm["headers"],
    )
    project_id = created.json()["id"]
    detail = client.get(f"/api/projects/{project_id}")

    assert created.status_code == 201
    assert created.json()["owner"]["username"] == "pmuser"  # người tạo = PM
    assert detail.status_code == 200
    assert detail.json()["name"] == "TaskHub"
    assert detail.json()["tasks"] == []


def test_get_unknown_project_returns_404(client):
    assert client.get("/api/projects/999").status_code == 404
    assert client.get("/api/projects/999/tasks").status_code == 404


def test_list_projects_is_paginated(client, make_user, make_project):
    pm = make_user("pmuser")
    for i in range(3):
        make_project(pm, name=f"Project {i}")

    resp = client.get("/api/projects", params={"skip": 1, "limit": 1})

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert [p["name"] for p in body["items"]] == ["Project 1"]
    assert body["items"][0]["owner"]["username"] == "pmuser"


def test_only_project_manager_or_admin_can_update_project(client, make_user, make_project):
    pm = make_user("pmuser")
    other = make_user("other")
    admin = make_user("boss", admin=True)
    project = make_project(pm)
    url = f"/api/projects/{project['id']}"

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

    resp = client.delete(f"/api/projects/{project['id']}", headers=pm["headers"])

    assert resp.status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
