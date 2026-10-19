"""Mục 2, 3, 4: CRUD project, nested response, tạo project cần đăng nhập."""


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
