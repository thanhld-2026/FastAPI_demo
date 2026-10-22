"""Phụ lục feature 3 + 11: workspace, thành viên, phân quyền OWNER / EDITOR / VIEWER."""

WS_URL = "/api/v1/workspaces"


def _member_url(workspace: dict, user: dict) -> str:
    return f"{WS_URL}/{workspace['id']}/members/{user['id']}"


# ---------- Workspace CRUD ----------
def test_create_workspace_makes_creator_owner(client, make_user):
    alice = make_user("alice")

    resp = client.post(WS_URL, json={"name": "Backend Team"}, headers=alice["headers"])

    body = resp.json()
    assert resp.status_code == 201
    assert body["owner"]["full_name"] == "alice"
    assert [(m["user"]["full_name"], m["role"]) for m in body["members"]] == [("alice", "OWNER")]
    assert client.post(WS_URL, json={"name": "X"}).status_code == 401


def test_list_and_read_workspaces_only_as_member(client, make_user, make_workspace):
    alice = make_user("alice")
    bob = make_user("bob")
    admin = make_user("boss", admin=True)
    mine = make_workspace(alice, name="Alice team")
    make_workspace(bob, name="Bob team")

    listed = client.get(WS_URL, headers=alice["headers"]).json()
    everything = client.get(WS_URL, headers=admin["headers"]).json()

    assert [w["name"] for w in listed["items"]] == ["Alice team"]
    assert everything["total"] == 2
    assert client.get(f"{WS_URL}/{mine['id']}", headers=bob["headers"]).status_code == 404
    assert client.get(f"{WS_URL}/{mine['id']}", headers=admin["headers"]).status_code == 200


def test_only_owner_can_rename_or_delete_workspace(
    client, make_user, make_workspace, make_project, add_member
):
    owner = make_user("owner")
    editor = make_user("editor")
    workspace = make_workspace(owner)
    add_member(workspace, owner, editor)
    url = f"{WS_URL}/{workspace['id']}"

    by_editor = client.patch(url, json={"name": "Hacked"}, headers=editor["headers"])
    renamed = client.patch(url, json={"name": "Renamed"}, headers=owner["headers"])
    null_name = client.patch(url, json={"name": None}, headers=owner["headers"])
    project = make_project(owner, workspace=workspace)
    still_has_projects = client.delete(url, headers=owner["headers"])
    client.delete(f"/api/v1/projects/{project['id']}", headers=owner["headers"])
    deleted = client.delete(url, headers=owner["headers"])

    assert by_editor.status_code == 403
    assert renamed.json()["name"] == "Renamed"
    assert null_name.status_code == 422
    assert still_has_projects.status_code == 409  # phải xóa project trước
    assert deleted.status_code == 204
    assert client.get(url, headers=owner["headers"]).status_code == 404


# ---------- Thành viên ----------
def test_invite_member(client, make_user, make_workspace):
    owner = make_user("owner")
    carol = make_user("carol")
    editor = make_user("editor")
    stranger = make_user("stranger")
    workspace = make_workspace(owner)
    url = f"{WS_URL}/{workspace['id']}/members"

    invited = client.post(url, json={"email": "Carol@Example.com"}, headers=owner["headers"])
    client.post(url, json={"email": editor["email"]}, headers=owner["headers"])
    by_editor = client.post(url, json={"email": stranger["email"]}, headers=editor["headers"])
    by_stranger = client.post(url, json={"email": carol["email"]}, headers=stranger["headers"])
    duplicate = client.post(url, json={"email": carol["email"]}, headers=owner["headers"])
    unknown = client.post(url, json={"email": "nobody@example.com"}, headers=owner["headers"])
    as_owner = client.post(
        url, json={"email": stranger["email"], "role": "OWNER"}, headers=owner["headers"]
    )

    assert invited.status_code == 201
    assert (invited.json()["user"]["full_name"], invited.json()["role"]) == ("carol", "EDITOR")
    assert by_editor.status_code == 403
    assert by_stranger.status_code == 404
    assert duplicate.status_code == 409
    assert unknown.status_code == 400  # body tham chiếu user không tồn tại
    assert as_owner.status_code == 422  # mỗi workspace chỉ có 1 OWNER


def test_change_member_role(client, make_user, make_workspace, add_member):
    owner = make_user("owner")
    carol = make_user("carol")
    workspace = make_workspace(owner)
    add_member(workspace, owner, carol, role="VIEWER")

    promoted = client.patch(
        _member_url(workspace, carol), json={"role": "EDITOR"}, headers=owner["headers"]
    )
    owner_change = client.patch(
        _member_url(workspace, owner), json={"role": "VIEWER"}, headers=owner["headers"]
    )
    missing = client.patch(
        f"{WS_URL}/{workspace['id']}/members/999", json={"role": "EDITOR"}, headers=owner["headers"]
    )

    assert promoted.json()["role"] == "EDITOR"
    assert owner_change.status_code == 400
    assert missing.status_code == 404


def test_remove_member_and_leave(client, make_user, make_workspace, add_member):
    owner = make_user("owner")
    carol = make_user("carol")
    dave = make_user("dave")
    workspace = make_workspace(owner)
    add_member(workspace, owner, carol)
    add_member(workspace, owner, dave, role="VIEWER")

    dave_removes_carol = client.delete(_member_url(workspace, carol), headers=dave["headers"])
    dave_leaves = client.delete(_member_url(workspace, dave), headers=dave["headers"])
    owner_removes_carol = client.delete(_member_url(workspace, carol), headers=owner["headers"])
    owner_leaves = client.delete(_member_url(workspace, owner), headers=owner["headers"])

    assert dave_removes_carol.status_code == 403
    assert dave_leaves.status_code == 204
    assert owner_removes_carol.status_code == 204
    assert owner_leaves.status_code == 400  # OWNER không rời được workspace của mình
    members = client.get(f"{WS_URL}/{workspace['id']}", headers=owner["headers"]).json()["members"]
    assert [m["user"]["full_name"] for m in members] == ["owner"]
    assert client.get(f"{WS_URL}/{workspace['id']}", headers=carol["headers"]).status_code == 404


def test_removing_member_unassigns_their_tasks(
    client, make_user, make_project, make_task, add_member
):
    owner = make_user("owner")
    carol = make_user("carol")
    project = make_project(owner)
    add_member(project, owner, carol)
    task = make_task(project["id"], owner)
    client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": carol["id"]},
        headers=owner["headers"],
    )

    client.delete(
        f"{WS_URL}/{project['workspace_id']}/members/{carol['id']}", headers=owner["headers"]
    )

    after = client.get(f"/api/v1/tasks/{task['id']}", headers=owner["headers"]).json()
    activities = client.get(
        f"/api/v1/tasks/{task['id']}/activities", headers=owner["headers"]
    ).json()["items"]
    assert after["assignee"] is None
    assert activities[-1]["detail"] == "unassigned (carol was removed from the workspace)"


def test_leaving_or_demoted_to_viewer_unassigns_tasks_of_active_projects(
    client, make_user, make_project, make_task, add_member
):
    owner = make_user("owner")
    carol = make_user("carol")
    dave = make_user("dave")
    project = make_project(owner)
    workspace = {"id": project["workspace_id"]}
    old_project = make_project(owner, name="Old", workspace=workspace)
    add_member(project, owner, carol)
    add_member(project, owner, dave)
    carol_task = make_task(project["id"], owner, title="Carol task")
    dave_task = make_task(project["id"], owner, title="Dave task")
    dave_old_task = make_task(old_project["id"], owner, title="Dave old task")
    for task, user in ((carol_task, carol), (dave_task, dave), (dave_old_task, dave)):
        client.post(
            f"/api/v1/tasks/{task['id']}/assign",
            json={"assignee_id": user["id"]},
            headers=owner["headers"],
        )
    client.post(f"/api/v1/projects/{old_project['id']}/archive", headers=owner["headers"])
    members_url = f"{WS_URL}/{workspace['id']}/members"

    left = client.delete(f"{members_url}/{carol['id']}", headers=carol["headers"])
    demoted = client.patch(
        f"{members_url}/{dave['id']}", json={"role": "VIEWER"}, headers=owner["headers"]
    )

    def last_activity(task: dict) -> tuple[str | None, str | None]:
        url = f"/api/v1/tasks/{task['id']}"
        current = client.get(url, headers=owner["headers"]).json()
        detail = client.get(f"{url}/activities", headers=owner["headers"]).json()["items"][-1]
        return (current["assignee"] or {}).get("full_name"), detail["detail"]

    assert (left.status_code, demoted.status_code) == (204, 200)
    assert last_activity(carol_task) == (None, "unassigned (carol left the workspace)")
    assert last_activity(dave_task) == (None, "unassigned (dave is now VIEWER)")
    # Project đã archive là chỉ đọc: giữ nguyên người làm task
    assert last_activity(dave_old_task) == ("dave", "assigned to dave")


# ---------- Dữ liệu không lộ sang workspace khác ----------
def test_tasks_of_other_workspaces_are_hidden(client, make_user, make_project, make_task):
    alice = make_user("alice")
    bob = make_user("bob")
    alice_task = make_task(make_project(alice)["id"], alice, title="Alice secret")
    make_task(make_project(bob)["id"], bob, title="Bob task")

    listed = client.get("/api/v1/tasks", headers=bob["headers"]).json()
    by_id = client.get(f"/api/v1/tasks/{alice_task['id']}", headers=bob["headers"])
    comments = client.get(f"/api/v1/tasks/{alice_task['id']}/comments", headers=bob["headers"])
    bookmark = client.post(f"/api/v1/tasks/{alice_task['id']}/bookmark", headers=bob["headers"])

    assert [t["title"] for t in listed["items"]] == ["Bob task"]
    assert (by_id.status_code, comments.status_code, bookmark.status_code) == (404, 404, 404)


def test_bookmarks_are_hidden_after_leaving_workspace(
    client, make_user, make_project, make_task, add_member
):
    owner = make_user("owner")
    carol = make_user("carol")
    project = make_project(owner)
    add_member(project, owner, carol, role="VIEWER")
    task = make_task(project["id"], owner)
    client.post(f"/api/v1/tasks/{task['id']}/bookmark", headers=carol["headers"])

    client.delete(
        f"{WS_URL}/{project['workspace_id']}/members/{carol['id']}", headers=carol["headers"]
    )

    bookmarks = client.get("/api/v1/users/me/bookmarks", headers=carol["headers"]).json()
    assert (bookmarks["total"], bookmarks["items"]) == (0, [])
