"""Khóa dòng khi archive / sửa project, chạy trên PostgreSQL thật.

SQLite (dùng cho các test khác) bỏ qua FOR SHARE / FOR UPDATE nên không kiểm tra được.
Chạy riêng (DB rỗng, test sẽ tạo / xóa bảng):

    TEST_POSTGRES_URL=postgresql+psycopg://user:pass@localhost:5432/taskhub_test pytest -m postgres
"""

import os
import threading
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app import crud
from app.database import Base
from app.models import Project, ProjectStatus, User

PG_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not PG_URL, reason="cần TEST_POSTGRES_URL (PostgreSQL thật)"),
]


@pytest.fixture
def pg_session_factory() -> Iterator[sessionmaker[Session]]:
    assert PG_URL is not None
    engine = create_engine(PG_URL)
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
