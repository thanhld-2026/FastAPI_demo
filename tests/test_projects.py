"""Mục 2, 3 + phụ lục 3-4: project trong workspace, nested response, quyền OWNER, archive."""


def test_create_project_requires_owner_of_workspace(
    client, make_user, make_workspace, add_member
):
    owner = make_user("owner")
    editor = make_user("editor")
    stranger = make_user("stranger")
    workspace = make_workspace(owner)
    add_member(workspace, owner, editor, role="EDITOR")
    url = f"/api/v1/workspaces/{workspace['id']}/projects"

    anonymous = client.post(url, json={"name": "X"})
    by_stranger = client.post(url, json={"name": "X"}, headers=stranger["headers"])
    by_editor = client.post(url, json={"name": "X"}, headers=editor["headers"])
    by_owner = client.post(
        url, json={"name": "TaskHub", "description": "Backend API"}, headers=owner["headers"]
    )

    assert anonymous.status_code == 401
    assert by_stranger.status_code == 404  # người ngoài không biết workspace có tồn tại
    assert by_editor.status_code == 403
    assert by_owner.status_code == 201
    assert by_owner.json()["workspace_id"] == workspace["id"]
    assert by_owner.json()["creator"]["username"] == "owner"


def test_get_project_detail_requires_membership(client, make_user, make_project, add_member):
    owner = make_user("owner")
    viewer = make_user("viewer")
    stranger = make_user("stranger")
    project = make_project(owner)
    add_member(project, owner, viewer, role="VIEWER")
    url = f"/api/v1/projects/{project['id']}"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=stranger["headers"]).status_code == 404
    assert client.get("/api/v1/projects/999", headers=owner["headers"]).status_code == 404
    detail = client.get(url, headers=viewer["headers"])
    assert detail.status_code == 200
    assert detail.json()["name"] == "TaskHub"
    assert detail.json()["tasks"] == []


def test_list_projects_only_shows_my_workspaces(client, make_user, make_project, add_member):
    alice = make_user("alice")
    bob = make_user("bob")
    admin = make_user("boss", admin=True)
    for i in range(3):
        make_project(alice, name=f"Project {i}")
    shared = make_project(bob, name="Bob shared")
    make_project(bob, name="Bob private")
    add_member(shared, bob, alice, role="VIEWER")

    page = client.get("/api/v1/projects", params={"page": 2, "limit": 1}, headers=alice["headers"])
    mine = client.get("/api/v1/projects", headers=alice["headers"]).json()
    everything = client.get("/api/v1/projects", headers=admin["headers"]).json()
    by_workspace = client.get(
        "/api/v1/projects",
        params={"workspace_id": shared["workspace_id"]},
        headers=alice["headers"],
    ).json()

    assert page.json()["total"] == 4
    assert [p["name"] for p in page.json()["items"]] == ["Project 1"]
    assert "Bob private" not in [p["name"] for p in mine["items"]]
    assert everything["total"] == 5  # admin thấy mọi workspace
    assert [p["name"] for p in by_workspace["items"]] == ["Bob shared"]


def test_project_detail_contains_nested_tasks_with_assignee(
    client, make_user, make_project, make_task, add_member
):
    owner = make_user("owner")
    dev = make_user("dev")
    project = make_project(owner)
    add_member(project, owner, dev)
    task = make_task(project["id"], owner, title="Design DB")
    client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": dev["id"]},
        headers=owner["headers"],
    )

    detail = client.get(f"/api/v1/projects/{project['id']}", headers=dev["headers"]).json()

    assert detail["creator"]["username"] == "owner"
    assert detail["tasks"][0]["title"] == "Design DB"
    assert detail["tasks"][0]["assignee"]["username"] == "dev"


def test_only_workspace_owner_or_admin_can_update_project(
    client, make_user, make_project, add_member
):
    owner = make_user("owner")
    editor = make_user("editor")
    stranger = make_user("stranger")
    admin = make_user("boss", admin=True)
    project = make_project(owner)
    add_member(project, owner, editor)
    url = f"/api/v1/projects/{project['id']}"

    by_stranger = client.put(url, json={"name": "Hacked"}, headers=stranger["headers"])
    by_editor = client.put(url, json={"name": "Hacked"}, headers=editor["headers"])
    by_owner = client.put(url, json={"name": "Renamed"}, headers=owner["headers"])
    by_admin = client.put(url, json={"description": "By admin"}, headers=admin["headers"])

    assert by_stranger.status_code == 404
    assert by_editor.status_code == 403
    assert by_owner.status_code == 200
    assert by_admin.status_code == 200
    assert by_admin.json()["name"] == "Renamed"  # partial update giữ nguyên field không gửi


def test_delete_project_cascades_to_tasks(client, make_user, make_project, make_task):
    owner = make_user("owner")
    project = make_project(owner)
    task = make_task(project["id"], owner)

    resp = client.delete(f"/api/v1/projects/{project['id']}", headers=owner["headers"])

    assert resp.status_code == 204
    headers = owner["headers"]
    assert client.get(f"/api/v1/projects/{project['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=headers).status_code == 404


def test_user_profile_only_shows_shared_workspaces(
    client, make_user, make_project, make_task, add_member
):
    owner = make_user("owner")
    dev = make_user("dev")
    outsider = make_user("outsider")
    project = make_project(owner, name="Mobile App")
    add_member(project, owner, dev)
    task = make_task(project["id"], owner, title="Login screen")
    client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": dev["id"]},
        headers=owner["headers"],
    )

    owner_profile = client.get("/api/v1/users/owner/profile", headers=dev["headers"]).json()
    dev_profile = client.get("/api/v1/users/dev/profile", headers=dev["headers"]).json()
    seen_by_outsider = client.get("/api/v1/users/dev/profile", headers=outsider["headers"]).json()

    assert [p["name"] for p in owner_profile["created_projects"]] == ["Mobile App"]
    assert owner_profile["created_projects"][0]["status"] == "ACTIVE"
    assert [t["title"] for t in dev_profile["assigned_tasks"]] == ["Login screen"]
    assert "email" not in dev_profile  # profile không lộ email
    # Người ngoài workspace không thấy task / project trong workspace đó qua profile
    assert seen_by_outsider["assigned_tasks"] == []
    assert client.get("/api/v1/users/dev/profile").status_code == 401
    assert client.get("/api/v1/users/ghost/profile", headers=dev["headers"]).status_code == 404


# ---------- Archive ----------
def test_archived_project_is_read_only(client, make_user, make_project, make_task, add_member):
    owner = make_user("owner")
    editor = make_user("editor")
    project = make_project(owner)
    add_member(project, owner, editor)
    task = make_task(project["id"], owner)
    url = f"/api/v1/projects/{project['id']}"
    task_url = f"/api/v1/tasks/{task['id']}"
    headers = owner["headers"]
    comment = client.post(
        f"{task_url}/comments", json={"content": "before archive"}, headers=headers
    ).json()
    comment_url = f"{task_url}/comments/{comment['id']}"

    by_editor = client.post(f"{url}/archive", headers=editor["headers"])
    archived = client.post(f"{url}/archive", headers=headers)
    again = client.post(f"{url}/archive", headers=headers)  # idempotent

    assert by_editor.status_code == 403
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert again.status_code == 200
    # Mọi thao tác ghi lên task / comment trong project đã archive -> 409
    writes = [
        client.post(f"{url}/tasks", json={"title": "X"}, headers=headers),
        client.put(task_url, json={"status": "DONE"}, headers=headers),
        client.post(f"{task_url}/assign", json={"assignee_id": editor["id"]}, headers=headers),
        client.post(f"{task_url}/comments", json={"content": "hi"}, headers=headers),
        client.put(comment_url, json={"content": "edited"}, headers=headers),
        client.delete(comment_url, headers=headers),
        client.delete(task_url, headers=headers),
    ]
    assert [r.status_code for r in writes] == [409] * len(writes)
    # Đọc vẫn bình thường
    assert client.get(f"{url}/tasks", headers=headers).status_code == 200
    assert client.get(task_url, headers=headers).status_code == 200


def test_unarchive_project_allows_writes_again(client, make_user, make_project):
    owner = make_user("owner")
    project = make_project(owner)
    url = f"/api/v1/projects/{project['id']}"
    headers = owner["headers"]
    client.post(f"{url}/archive", headers=headers)

    reopened = client.post(f"{url}/unarchive", headers=headers)
    created = client.post(f"{url}/tasks", json={"title": "Back to work"}, headers=headers)
    renamed = client.put(url, json={"name": "Renamed"}, headers=headers)

    assert reopened.json()["status"] == "ACTIVE"
    assert created.status_code == 201
    assert renamed.status_code == 200


def test_archived_project_itself_cannot_be_changed_or_deleted(
    client, make_user, make_project, make_task
):
    owner = make_user("owner")
    project = make_project(owner)
    task = make_task(project["id"], owner)
    url = f"/api/v1/projects/{project['id']}"
    headers = owner["headers"]
    client.post(f"{url}/archive", headers=headers)

    renamed = client.put(url, json={"name": "Renamed"}, headers=headers)
    deleted = client.delete(url, headers=headers)

    assert renamed.status_code == 409
    assert deleted.status_code == 409
    assert client.get(url, headers=headers).json()["name"] == "TaskHub"
    # task không bị xóa theo
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=headers).status_code == 200


def test_error_order_on_archived_project(client, make_user, make_project, make_task, add_member):
    """401 -> 404 (không tồn tại / không phải thành viên) -> 409 (archive) -> 403 (role)."""
    owner = make_user("owner")
    viewer = make_user("viewer")
    stranger = make_user("stranger")
    project = make_project(owner)
    add_member(project, owner, viewer, role="VIEWER")
    task = make_task(project["id"], owner)
    task_url = f"/api/v1/tasks/{task['id']}"
    body = {"status": "DONE"}

    not_archived_viewer = client.put(task_url, json=body, headers=viewer["headers"])
    client.post(f"/api/v1/projects/{project['id']}/archive", headers=owner["headers"])
    anonymous = client.put(task_url, json=body)
    missing = client.put("/api/v1/tasks/999", json=body, headers=owner["headers"])
    by_stranger = client.put(task_url, json=body, headers=stranger["headers"])
    by_viewer = client.put(task_url, json=body, headers=viewer["headers"])

    assert not_archived_viewer.status_code == 403
    codes = (anonymous, missing, by_stranger, by_viewer)
    assert [r.status_code for r in codes] == [401, 404, 404, 409]


def test_filter_projects_by_status(client, make_user, make_project):
    owner = make_user("owner")
    headers = owner["headers"]
    make_project(owner, name="Active one")
    old = make_project(owner, name="Old one")
    client.post(f"/api/v1/projects/{old['id']}/archive", headers=headers)

    active = client.get("/api/v1/projects", params={"status": "ACTIVE"}, headers=headers).json()
    archived = client.get("/api/v1/projects", params={"status": "ARCHIVED"}, headers=headers)

    assert [p["name"] for p in active["items"]] == ["Active one"]
    assert [p["name"] for p in archived.json()["items"]] == ["Old one"]
    invalid = client.get("/api/v1/projects", params={"status": "DELETED"}, headers=headers)
    assert invalid.status_code == 422
