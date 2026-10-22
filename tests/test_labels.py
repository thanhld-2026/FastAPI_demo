"""Phụ lục feature 6: label theo project, gắn / gỡ label cho task."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.models import Task


@dataclass
class Setup:
    owner: dict
    editor: dict
    viewer: dict
    project: dict


@pytest.fixture
def setup(make_user, make_project, add_member) -> Setup:
    owner = make_user("owner")
    editor = make_user("editor")
    viewer = make_user("viewer")
    project = make_project(owner)
    add_member(project, owner, editor, role="EDITOR")
    add_member(project, owner, viewer, role="VIEWER")
    return Setup(owner, editor, viewer, project)


def _labels_url(project: dict) -> str:
    return f"/api/v1/projects/{project['id']}/labels"


# ---------- CRUD ----------
def test_editor_manages_labels_viewer_only_reads(client, make_user, setup):
    url = _labels_url(setup.project)
    stranger = make_user("stranger")

    by_viewer = client.post(url, json={"name": "bug"}, headers=setup.viewer["headers"])
    by_stranger = client.post(url, json={"name": "bug"}, headers=stranger["headers"])
    created = client.post(
        url, json={"name": "bug", "color": "#DC2626"}, headers=setup.editor["headers"]
    )
    listed = client.get(url, headers=setup.viewer["headers"])

    assert (by_viewer.status_code, by_stranger.status_code) == (403, 404)
    assert created.status_code == 201
    assert created.json()["color"] == "#dc2626"  # chuẩn hóa chữ thường
    assert [(lb["name"], lb["project_id"]) for lb in listed.json()] == [
        ("bug", setup.project["id"])
    ]
    assert client.get(url, headers=stranger["headers"]).status_code == 404


def test_label_name_is_unique_per_project(client, make_project, make_label, setup):
    other_project = make_project(setup.owner, name="Other")
    make_label(setup.project, setup.owner, "bug")

    duplicate = client.post(
        _labels_url(setup.project), json={"name": "bug"}, headers=setup.owner["headers"]
    )
    same_name_elsewhere = client.post(
        _labels_url(other_project), json={"name": "bug"}, headers=setup.owner["headers"]
    )

    assert duplicate.status_code == 409
    assert same_name_elsewhere.status_code == 201  # 2 project khác nhau có thể cùng tên


def test_label_names_ignore_case(client, setup):
    url = _labels_url(setup.project)
    headers = setup.owner["headers"]

    created = client.post(url, json={"name": " Bug "}, headers=headers)
    duplicate = client.post(url, json={"name": "BUG"}, headers=headers)

    assert created.json()["name"] == "bug"  # cắt khoảng trắng + chữ thường
    assert duplicate.status_code == 409


def test_label_input_is_validated(client, setup):
    url = _labels_url(setup.project)
    headers = setup.owner["headers"]

    assert client.post(url, json={"name": ""}, headers=headers).status_code == 422
    assert client.post(url, json={"name": "x" * 31}, headers=headers).status_code == 422
    bad_color = client.post(url, json={"name": "bug", "color": "red"}, headers=headers)
    assert bad_color.status_code == 422


def test_update_and_delete_label(client, make_label, make_task, setup):
    label = make_label(setup.project, setup.owner, "bug")
    taken = make_label(setup.project, setup.owner, "feature")
    task = make_task(setup.project["id"], setup.owner, label_ids=[label["id"]])
    url = f"/api/v1/labels/{label['id']}"

    renamed = client.patch(url, json={"name": "defect"}, headers=setup.editor["headers"])
    clash = client.patch(url, json={"name": taken["name"]}, headers=setup.editor["headers"])
    null_color = client.patch(url, json={"color": None}, headers=setup.editor["headers"])
    by_viewer = client.delete(url, headers=setup.viewer["headers"])
    deleted = client.delete(url, headers=setup.editor["headers"])
    after = client.get(f"/api/v1/tasks/{task['id']}", headers=setup.owner["headers"]).json()

    assert renamed.json()["name"] == "defect"
    assert clash.status_code == 409
    assert null_color.status_code == 422
    assert by_viewer.status_code == 403
    assert deleted.status_code == 204
    assert after["labels"] == []  # xóa label -> tự gỡ khỏi task
    assert client.delete(url, headers=setup.owner["headers"]).status_code == 404


# ---------- Gắn / gỡ label cho task ----------
def test_attach_and_detach_label(client, make_label, make_task, setup):
    label = make_label(setup.project, setup.owner, "bug")
    task = make_task(setup.project["id"], setup.owner)
    url = f"/api/v1/tasks/{task['id']}/labels/{label['id']}"

    by_viewer = client.post(url, headers=setup.viewer["headers"])
    attached = client.post(url, headers=setup.editor["headers"])
    again = client.post(url, headers=setup.editor["headers"])  # idempotent
    detached = client.delete(url, headers=setup.editor["headers"])
    activities = client.get(
        f"/api/v1/tasks/{task['id']}/activities", headers=setup.owner["headers"]
    ).json()["items"]

    assert by_viewer.status_code == 403
    assert [lb["name"] for lb in attached.json()["labels"]] == ["bug"]
    assert again.status_code == 200
    assert detached.json()["labels"] == []
    # Gắn 2 lần chỉ ghi 1 activity
    assert [a["detail"] for a in activities[1:]] == ["added label bug", "removed label bug"]


def test_labels_of_another_project_cannot_be_used(
    client, make_project, make_label, make_task, setup
):
    other_project = make_project(setup.owner, name="Other")
    foreign = make_label(other_project, setup.owner, "foreign")
    task = make_task(setup.project["id"], setup.owner)
    headers = setup.owner["headers"]

    attach = client.post(f"/api/v1/tasks/{task['id']}/labels/{foreign['id']}", headers=headers)
    create = client.post(
        f"/api/v1/projects/{setup.project['id']}/tasks",
        json={"title": "X", "label_ids": [foreign["id"]]},
        headers=headers,
    )
    update = client.put(
        f"/api/v1/tasks/{task['id']}", json={"label_ids": [foreign["id"]]}, headers=headers
    )

    assert attach.status_code == 404  # label trên URL không thuộc project của task
    assert create.status_code == 400  # body tham chiếu label không thuộc project
    assert update.status_code == 400


def test_labels_of_archived_project_are_read_only(client, make_label, make_task, setup):
    label = make_label(setup.project, setup.owner, "bug")
    task = make_task(setup.project["id"], setup.owner)
    headers = setup.owner["headers"]
    client.post(f"/api/v1/projects/{setup.project['id']}/archive", headers=headers)

    writes = [
        client.post(_labels_url(setup.project), json={"name": "new"}, headers=headers),
        client.patch(f"/api/v1/labels/{label['id']}", json={"name": "x"}, headers=headers),
        client.delete(f"/api/v1/labels/{label['id']}", headers=headers),
        client.post(f"/api/v1/tasks/{task['id']}/labels/{label['id']}", headers=headers),
    ]

    assert [r.status_code for r in writes] == [409] * len(writes)
    assert client.get(_labels_url(setup.project), headers=headers).status_code == 200


def test_deleting_label_is_logged_on_each_task(client, db, make_label, make_task, setup):
    label = make_label(setup.project, setup.owner, "bug")
    tasks = [
        make_task(setup.project["id"], setup.owner, title=title, label_ids=[label["id"]])
        for title in ("A", "B")
    ]
    untouched = make_task(setup.project["id"], setup.owner, title="C")
    long_ago = datetime(2020, 1, 1, tzinfo=UTC)
    db.execute(update(Task).values(updated_at=long_ago))
    db.commit()

    client.delete(f"/api/v1/labels/{label['id']}", headers=setup.editor["headers"])

    def last(task: dict) -> tuple[str | None, bool]:
        url = f"/api/v1/tasks/{task['id']}"
        headers = setup.owner["headers"]
        activity = client.get(f"{url}/activities", headers=headers).json()["items"][-1]
        changed = datetime.fromisoformat(client.get(url, headers=headers).json()["updated_at"])
        return activity["detail"], changed > long_ago

    assert [last(task) for task in tasks] == [("removed label bug (label deleted)", True)] * 2
    assert last(untouched) == (None, False)


def test_changing_labels_updates_task_timestamp(client, db, make_label, make_task, setup):
    label = make_label(setup.project, setup.owner, "bug")
    task = make_task(setup.project["id"], setup.owner)
    url = f"/api/v1/tasks/{task['id']}"
    long_ago = datetime(2020, 1, 1, tzinfo=UTC)

    def updated_after(action) -> bool:
        db.execute(update(Task).values(updated_at=long_ago))
        db.commit()
        action()
        body = client.get(url, headers=setup.owner["headers"]).json()
        return datetime.fromisoformat(body["updated_at"]) > long_ago

    headers = setup.editor["headers"]
    attach = updated_after(lambda: client.post(f"{url}/labels/{label['id']}", headers=headers))
    detach = updated_after(lambda: client.delete(f"{url}/labels/{label['id']}", headers=headers))
    via_put = updated_after(
        lambda: client.put(url, json={"label_ids": [label["id"]]}, headers=headers)
    )

    assert (attach, detach, via_put) == (True, True, True)
