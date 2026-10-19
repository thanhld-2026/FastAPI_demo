"""Cấu hình chung cho test.

- Dùng SQLite in-memory thay cho PostgreSQL: test chạy nhanh, độc lập, không cần cài DB.
- Mỗi test có database trống riêng (create_all trước test, drop_all sau test).
- Ghi đè dependency get_db bằng app.dependency_overrides -> API dùng DB test.
"""

import os

# Phải set biến môi trường TRƯỚC khi import app (Settings đọc env lúc import).
# Gán trực tiếp (không dùng setdefault) để đè giá trị trong file .env.
os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "SECRET_KEY": "test-secret-key-that-is-at-least-32-characters-long",
        "BCRYPT_ROUNDS": "4",  # hash nhanh hơn cho test (production dùng 12)
    }
)

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# StaticPool: mọi session dùng chung 1 connection -> cùng nhìn thấy 1 DB in-memory
engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _):
    # SQLite mặc định KHÔNG kiểm tra foreign key, bật lên để giống PostgreSQL
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


TestingSessionLocal = sessionmaker(bind=engine, autoflush=False)

DEFAULT_PASSWORD = "Password123"


@pytest.fixture(autouse=True)
def _setup_database() -> Iterator[None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Iterator[Session]:
    """Session để test đọc/ghi DB trực tiếp (setup dữ liệu, kiểm tra kết quả)."""
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(client: TestClient) -> Callable[..., dict]:
    """Factory: đăng ký + đăng nhập 1 user qua API.

    Trả về dict: {"id", "username", "email", "headers"} với headers chứa Bearer token.
    """

    def _make_user(username: str, *, password: str = DEFAULT_PASSWORD) -> dict:
        resp = client.post(
            "/api/users/register",
            json={"username": username, "email": f"{username}@example.com", "password": password},
        )
        assert resp.status_code == 201, resp.text
        user = resp.json()

        resp = client.post("/api/users/login", data={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return {**user, "headers": {"Authorization": f"Bearer {token}"}}

    return _make_user


@pytest.fixture
def make_project(client: TestClient) -> Callable[..., dict]:
    def _make_project(owner: dict, name: str = "TaskHub") -> dict:
        resp = client.post("/api/projects", json={"name": name}, headers=owner["headers"])
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_project


@pytest.fixture
def make_task(client: TestClient) -> Callable[..., dict]:
    def _make_task(project_id: int, creator: dict, **fields) -> dict:
        payload = {"title": "A task", **fields}
        resp = client.post(
            f"/api/projects/{project_id}/tasks", json=payload, headers=creator["headers"]
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_task
