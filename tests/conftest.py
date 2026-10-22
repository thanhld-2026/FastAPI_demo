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
        "REDIS_URL": "",
        "EMAIL_ENABLED": "false",
        "BCRYPT_ROUNDS": "4",  # hash nhanh hơn cho test (production dùng 12)
        "LOG_FILE": "",
        "LOG_LEVEL": "WARNING",
    }
)

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole

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
def make_user(client: TestClient, db: Session) -> Callable[..., dict]:
    """Factory: đăng ký + đăng nhập 1 user qua API.

    `name` dùng làm full_name, email là <name>@example.com.
    Trả về dict: {"id", "full_name", "email", "headers", "refresh_token"},
    headers chứa Bearer access token.
    """

    def _make_user(name: str, *, admin: bool = False, password: str = DEFAULT_PASSWORD) -> dict:
        email = f"{name}@example.com"
        resp = client.post(
            "/api/v1/auth/register",
            json={"full_name": name, "email": email, "password": password},
        )
        assert resp.status_code == 201, resp.text
        user = resp.json()

        if admin:
            db.execute(update(User).where(User.id == user["id"]).values(role=UserRole.ADMIN))
            db.commit()

        resp = client.post("/api/v1/auth/login", data={"username": email, "password": password})
        assert resp.status_code == 200, resp.text
        tokens = resp.json()
        return {
            **user,
            "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
            "refresh_token": tokens["refresh_token"],
        }

    return _make_user


@pytest.fixture
def make_tag(client: TestClient, make_user) -> Callable[[str], dict]:
    admin = None

    def _make_tag(name: str) -> dict:
        nonlocal admin
        admin = admin or make_user("tag_admin", admin=True)
        resp = client.post("/api/v1/tags", json={"name": name}, headers=admin["headers"])
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_tag


@pytest.fixture
def make_workspace(client: TestClient) -> Callable[..., dict]:
    def _make_workspace(owner: dict, name: str = "Team") -> dict:
        resp = client.post("/api/v1/workspaces", json={"name": name}, headers=owner["headers"])
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_workspace


@pytest.fixture
def make_project(client: TestClient, make_workspace) -> Callable[..., dict]:
    """Tạo project; không truyền workspace thì tạo luôn 1 workspace mới do `owner` làm OWNER."""

    def _make_project(owner: dict, name: str = "TaskHub", workspace: dict | None = None) -> dict:
        workspace = workspace or make_workspace(owner, name=f"{name} team")
        resp = client.post(
            f"/api/v1/workspaces/{workspace['id']}/projects",
            json={"name": name},
            headers=owner["headers"],
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_project


@pytest.fixture
def add_member(client: TestClient) -> Callable[..., dict]:
    """OWNER mời `member` vào workspace. `target` là workspace hoặc project (dùng workspace_id)."""

    def _add_member(target: dict, owner: dict, member: dict, role: str = "EDITOR") -> dict:
        workspace_id = target.get("workspace_id", target["id"])
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"email": member["email"], "role": role},
            headers=owner["headers"],
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _add_member


@pytest.fixture
def make_task(client: TestClient) -> Callable[..., dict]:
    def _make_task(project_id: int, creator: dict, **fields) -> dict:
        payload = {"title": "A task", **fields}
        resp = client.post(
            f"/api/v1/projects/{project_id}/tasks", json=payload, headers=creator["headers"]
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make_task


@pytest.fixture
def sql_log() -> Iterator[list[str]]:
    """Ghi lại mọi câu SQL đã chạy -> dùng để đếm query, chứng minh không bị N+1."""
    statements: list[str] = []

    def _before_execute(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before_execute)
    yield statements
    event.remove(engine, "before_cursor_execute", _before_execute)
