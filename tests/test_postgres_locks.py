"""Khóa dòng (archive / sửa project, giao task / đổi role thành viên, gắn / xóa label), chạy trên
PostgreSQL thật.

SQLite (dùng cho các test khác) bỏ qua FOR SHARE / FOR UPDATE nên không kiểm tra được.
Chạy riêng, trên 1 DB chỉ dành cho test (test sẽ XÓA / tạo lại toàn bộ bảng, nên tên DB bắt
buộc kết thúc bằng `_test`):

    TEST_POSTGRES_URL=postgresql+psycopg://user:pass@localhost:5432/taskhub_test pytest -m postgres

Có 2 tầng: test crud (2 session tự tay giữ khóa) và test HTTP (đi qua router + dependency thật,
app dùng PostgreSQL thay cho SQLite).
"""

import os
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app import crud
from app.database import Base, get_db
from app.main import app
from app.models import (
    ActivityAction,
    Label,
    Project,
    ProjectStatus,
    Task,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from tests.conftest import DEFAULT_PASSWORD

PG_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not PG_URL, reason="cần TEST_POSTGRES_URL (PostgreSQL thật)"),
]


def _test_database_url() -> str:
    """drop_all xóa sạch DB: chỉ chạy khi URL trỏ tới DB có tên kết thúc bằng `_test`, để lỡ
    trỏ nhầm DB dev / production thì test dừng ngay chứ không xóa dữ liệu."""
    assert PG_URL is not None
    name = make_url(PG_URL).database or ""
    if not name.endswith("_test"):
        pytest.fail(f"TEST_POSTGRES_URL phải trỏ tới DB riêng cho test (*_test), đang là {name!r}")
    return PG_URL


@pytest.fixture
def pg_session_factory() -> Iterator[sessionmaker[Session]]:
    # lock_timeout: lỡ có bug làm 2 bên chờ nhau thì test báo lỗi sau 5 giây thay vì treo mãi
    engine = create_engine(
        _test_database_url(), connect_args={"options": "-c lock_timeout=5s"}
    )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@dataclass
class Ids:
    project: int
    workspace: int
    editor: int
    task: int
    label: int


@pytest.fixture
def ids(pg_session_factory: sessionmaker[Session]) -> Ids:
    """Workspace (owner + 1 EDITOR) chứa 1 project, có 1 task và 1 label."""
    with pg_session_factory() as db:
        owner = User(full_name="owner", email="owner@example.com", hashed_password="x")
        editor = User(full_name="carol", email="carol@example.com", hashed_password="x")
        workspace = Workspace(name="Team", owner=owner)
        workspace.members.append(WorkspaceMember(user=owner, role=WorkspaceRole.OWNER))
        workspace.members.append(WorkspaceMember(user=editor, role=WorkspaceRole.EDITOR))
        project = Project(name="TaskHub", workspace=workspace, creator=owner)
        task = Task(title="Login API", project=project, creator=owner)
        label = Label(name="bug", color="#dc2626", project=project)
        db.add_all([task, label])
        db.commit()
        return Ids(project.id, workspace.id, editor.id, task.id, label.id)


@pytest.fixture
def project_id(ids: Ids) -> int:
    return ids.project


def _archive(db: Session, project_id: int) -> None:
    db.execute(
        update(Project).where(Project.id == project_id).values(status=ProjectStatus.ARCHIVED)
    )


def test_archive_waits_for_a_running_write(pg_session_factory, project_id):
    writer = pg_session_factory()
    archiver = pg_session_factory()
    try:
        assert crud.project.lock_status(writer, project_id) == ProjectStatus.ACTIVE  # FOR SHARE
        archiver.execute(text("SET lock_timeout = '300ms'"))

        with pytest.raises(OperationalError):  # LockNotAvailable: phải chờ writer commit
            _archive(archiver, project_id)
    finally:
        archiver.rollback()
        writer.rollback()
        writer.close()
        archiver.close()


def test_write_arriving_during_archive_sees_archived(pg_session_factory, project_id):
    archiver = pg_session_factory()
    _archive(archiver, project_id)  # chưa commit, đang giữ khóa dòng
    seen: dict[str, object] = {}

    def late_writer() -> None:
        with pg_session_factory() as db:
            started = time.perf_counter()
            seen["status"] = crud.project.lock_status(db, project_id)
            seen["waited"] = time.perf_counter() - started
            db.rollback()

    thread = threading.Thread(target=late_writer)
    thread.start()
    time.sleep(0.3)
    archiver.commit()
    archiver.close()
    thread.join(timeout=5)

    assert seen["status"] == ProjectStatus.ARCHIVED
    assert seen["waited"] >= 0.2  # đã phải chờ archive commit


def test_get_for_update_reloads_the_locked_row(pg_session_factory, project_id):
    """Bản load trước khi có khóa có thể đã cũ: get_for_update phải đọc lại dữ liệu mới nhất."""
    late = pg_session_factory()
    try:
        stale = late.get(Project, project_id)
        assert stale is not None and stale.name == "TaskHub"
        with pg_session_factory() as other:
            other.execute(update(Project).where(Project.id == project_id).values(name="Renamed"))
            other.commit()

        locked = crud.project.get_for_update(late, project_id)

        assert locked is stale  # cùng 1 object trong session...
        assert locked is not None and locked.name == "Renamed"  # ...nhưng đã được đọc lại
    finally:
        late.rollback()  # luôn nhả khóa, kể cả khi assert fail (nếu không, teardown bị treo)
        late.close()


def test_member_cannot_be_demoted_while_a_task_is_being_assigned_to_them(pg_session_factory, ids):
    """Giao task đọc role người nhận bằng FOR SHARE -> đổi role / xóa thành viên (FOR UPDATE
    dòng membership) phải chờ, không thể giao task cho người vừa bị hạ xuống VIEWER."""
    assigner = pg_session_factory()
    owner = pg_session_factory()
    try:
        role = crud.workspace.get_role_for_project(assigner, ids.project, ids.editor, lock=True)
        assert role == WorkspaceRole.EDITOR
        owner.execute(text("SET lock_timeout = '300ms'"))

        with pytest.raises(OperationalError):
            crud.workspace.get_member(owner, ids.workspace, ids.editor, lock=True)
    finally:
        owner.rollback()
        assigner.rollback()
        assigner.close()
        owner.close()


def test_label_cannot_be_deleted_while_being_attached(pg_session_factory, ids):
    """Gắn label đọc label bằng FOR SHARE -> xóa label (FOR UPDATE) phải chờ: không có cảnh
    INSERT task_labels trỏ tới label vừa bị xóa (lỗi khóa ngoại -> 500)."""
    attacher = pg_session_factory()
    deleter = pg_session_factory()
    try:
        assert crud.label.get_in_project(attacher, ids.project, ids.label, for_share=True)
        deleter.execute(text("SET lock_timeout = '300ms'"))

        with pytest.raises(OperationalError):
            crud.label.get_for_update(deleter, ids.label)
    finally:
        deleter.rollback()
        attacher.rollback()
        attacher.close()
        deleter.close()


def test_label_changes_of_one_task_run_one_at_a_time(pg_session_factory, ids):
    """2 request đổi label của cùng 1 task chạy lần lượt (FOR NO KEY UPDATE dòng task), nhưng
    không chặn request khác ghi activity / comment cho task đó (khóa ngoại tới task)."""
    first = pg_session_factory()
    second = pg_session_factory()
    other = pg_session_factory()
    try:
        crud.task.lock_label_set(first, first.get_one(Task, ids.task))
        second.execute(text("SET lock_timeout = '300ms'"))
        other.execute(text("SET lock_timeout = '300ms'"))

        with pytest.raises(OperationalError):
            crud.task.lock_label_set(second, second.get_one(Task, ids.task))
        crud.activity.add(
            other,
            task=other.get_one(Task, ids.task),
            actor=other.get_one(User, ids.editor),
            action=ActivityAction.COMMENTED,
        )
        other.flush()  # INSERT có khóa ngoại tới task: không phải chờ
    finally:
        for session in (other, second, first):
            session.rollback()
            session.close()


# ---------- Đi qua HTTP: router + dependency thật ----------
@pytest.fixture
def pg_client(pg_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        session = pg_session_factory()
        try:
            yield session
        finally:
            session.close()  # đóng session = rollback phần chưa commit, nhả khóa

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _register(client: TestClient, name: str) -> tuple[dict[str, str], int]:
    """Đăng ký + đăng nhập qua API. Trả về (headers, user_id)."""
    email = f"{name}@example.com"
    register = client.post(
        "/api/v1/auth/register",
        json={"full_name": name, "email": email, "password": DEFAULT_PASSWORD},
    )
    # Form OAuth2: field tên `username`, giá trị là email
    login = client.post(
        "/api/v1/auth/login", data={"username": email, "password": DEFAULT_PASSWORD}
    )
    assert (register.status_code, login.status_code) == (201, 200), login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, register.json()["id"]


def _owner_with_project(client: TestClient) -> tuple[dict[str, str], int]:
    """Tạo user làm OWNER của 1 workspace + 1 project. Trả về (headers, project_id)."""
    headers, _ = _register(client, "pm")
    workspace = client.post("/api/v1/workspaces", json={"name": "Team"}, headers=headers).json()
    project = client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects", json={"name": "TaskHub"}, headers=headers
    )
    return headers, project.json()["id"]


def _in_thread(call) -> tuple[threading.Thread, dict]:
    """Chạy `call()` ở thread khác, ghi lại response và thời gian đã chờ."""
    result: dict = {}

    def run() -> None:
        started = time.perf_counter()
        result["response"] = call()
        result["waited"] = time.perf_counter() - started

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


def test_http_task_created_during_archive_waits_then_gets_409(pg_client, pg_session_factory):
    headers, project_id = _owner_with_project(pg_client)
    archiver = pg_session_factory()
    try:
        _archive(archiver, project_id)  # archive chưa commit, đang giữ khóa dòng project
        thread, result = _in_thread(
            lambda: pg_client.post(
                f"/api/v1/projects/{project_id}/tasks", json={"title": "late"}, headers=headers
            )
        )
        time.sleep(0.3)
        assert thread.is_alive()  # POST /tasks đang chờ khóa, chưa trả về
        archiver.commit()
        thread.join(timeout=10)
    finally:
        archiver.rollback()
        archiver.close()

    assert result["response"].status_code == 409  # thấy status mới, không tạo task lọt vào
    assert result["waited"] >= 0.2


def test_http_archive_waits_for_a_running_task_write(pg_client, pg_session_factory):
    headers, project_id = _owner_with_project(pg_client)
    writer = pg_session_factory()
    try:
        # Giả lập 1 request ghi task đang chạy dở: đã giữ FOR SHARE trên dòng project
        assert crud.project.lock_status(writer, project_id) == ProjectStatus.ACTIVE
        thread, result = _in_thread(
            lambda: pg_client.post(f"/api/v1/projects/{project_id}/archive", headers=headers)
        )
        time.sleep(0.3)
        assert thread.is_alive()  # archive phải chờ request ghi xong
        writer.commit()
        thread.join(timeout=10)
    finally:
        writer.rollback()
        writer.close()

    assert result["response"].status_code == 200
    assert result["response"].json()["status"] == "ARCHIVED"
    assert result["waited"] >= 0.2


def test_http_transfer_ownership_respects_the_one_owner_index(pg_client):
    """Unique index "1 OWNER / workspace" của PostgreSQL kiểm tra ngay từng câu UPDATE: chuyển
    quyền phải hạ owner cũ trước rồi mới nâng người mới, nếu không sẽ lỗi 500."""
    owner, _ = _register(pg_client, "alice")
    _, bob_id = _register(pg_client, "bob")
    workspace = pg_client.post("/api/v1/workspaces", json={"name": "Team"}, headers=owner).json()
    url = f"/api/v1/workspaces/{workspace['id']}"
    pg_client.post(f"{url}/members", json={"email": "bob@example.com"}, headers=owner)

    resp = pg_client.post(f"{url}/transfer-ownership", json={"user_id": bob_id}, headers=owner)

    roles = {m["user"]["full_name"]: m["role"] for m in resp.json()["members"]}
    assert resp.status_code == 200
    assert roles == {"alice": "EDITOR", "bob": "OWNER"}
