"""Khóa dòng khi archive / sửa project, chạy trên PostgreSQL thật.

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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app import crud
from app.database import Base, get_db
from app.main import app
from app.models import Project, ProjectStatus, User
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


@pytest.fixture
def project_id(pg_session_factory: sessionmaker[Session]) -> int:
    with pg_session_factory() as db:
        owner = User(full_name="pm", email="pm@example.com", hashed_password="x")
        project = Project(name="TaskHub", owner=owner)
        db.add(project)
        db.commit()
        return project.id


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


def _pm_with_project(client: TestClient) -> tuple[dict[str, str], int]:
    """Đăng ký + đăng nhập PM qua API, tạo 1 project. Trả về (headers, project_id)."""
    register = client.post(
        "/api/v1/auth/register",
        json={"full_name": "pm", "email": "pm@example.com", "password": DEFAULT_PASSWORD},
    )
    # Form OAuth2: field tên `username`, giá trị là email
    login = client.post(
        "/api/v1/auth/login", data={"username": "pm@example.com", "password": DEFAULT_PASSWORD}
    )
    assert (register.status_code, login.status_code) == (201, 200), login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    project = client.post("/api/v1/projects", json={"name": "TaskHub"}, headers=headers)
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
    headers, project_id = _pm_with_project(pg_client)
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
    headers, project_id = _pm_with_project(pg_client)
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
