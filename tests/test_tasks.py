"""Mục 3, 4: Tạo task trong project (cần đăng nhập), gắn tag."""


def test_create_task_requires_login(client, make_user, make_project):
    project = make_project(make_user("pmuser"))

    resp = client.post(f"/api/projects/{project['id']}/tasks", json={"title": "X"})

    assert resp.status_code == 401


def test_create_task_with_unknown_tag_returns_400(client, make_user, make_project):
    pm = make_user("pmuser")
    project = make_project(pm)

    resp = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "X", "tag_ids": [999]},
        headers=pm["headers"],
    )

    assert resp.status_code == 400
