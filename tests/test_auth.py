"""Mục 4 & 5: Đăng ký / đăng nhập JWT, bảo vệ endpoint, phân quyền admin."""

from datetime import timedelta

from sqlalchemy import update

from app.models import User
from app.security import create_access_token
from tests.conftest import DEFAULT_PASSWORD


def test_register_returns_user_without_password(client):
    resp = client.post(
        "/api/users/register",
        json={"username": "alice", "email": "Alice@Example.com", "password": DEFAULT_PASSWORD},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"  # email được chuẩn hóa chữ thường
    assert body["role"] == "member"
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_username_or_email_returns_409(client, make_user):
    make_user("alice")

    same_username = client.post(
        "/api/users/register",
        json={"username": "alice", "email": "other@example.com", "password": DEFAULT_PASSWORD},
    )
    same_email = client.post(
        "/api/users/register",
        json={"username": "alice2", "email": "alice@example.com", "password": DEFAULT_PASSWORD},
    )

    assert same_username.status_code == 409
    assert same_email.status_code == 409


def test_register_rejects_mass_assignment_of_role(client):
    resp = client.post(
        "/api/users/register",
        json={
            "username": "hacker",
            "email": "hacker@example.com",
            "password": DEFAULT_PASSWORD,
            "role": "admin",
        },
    )
    assert resp.status_code == 422


def test_register_validates_input(client):
    resp = client.post(
        "/api/users/register",
        json={"username": "a b", "email": "not-an-email", "password": "short"},
    )

    assert resp.status_code == 422
    invalid_fields = {err["loc"][-1] for err in resp.json()["detail"]}
    assert invalid_fields == {"username", "email", "password"}


def test_login_with_username_or_email(client, make_user):
    make_user("alice")

    by_username = client.post(
        "/api/users/login", data={"username": "alice", "password": DEFAULT_PASSWORD}
    )
    by_email = client.post(
        "/api/users/login", data={"username": "alice@example.com", "password": DEFAULT_PASSWORD}
    )

    assert by_username.status_code == 200
    assert by_username.json()["token_type"] == "bearer"
    assert by_email.status_code == 200


def test_login_with_wrong_password_returns_401(client, make_user):
    make_user("alice")

    resp = client.post("/api/users/login", data={"username": "alice", "password": "WrongPass1"})
    unknown = client.post("/api/users/login", data={"username": "nobody", "password": "WrongPass1"})

    assert resp.status_code == 401
    assert unknown.status_code == 401  # không tiết lộ username có tồn tại hay không


def test_me_requires_valid_token(client, make_user):
    alice = make_user("alice")

    no_token = client.get("/api/users/me")
    bad_token = client.get("/api/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    expired = create_access_token(alice["id"], expires_delta=timedelta(seconds=-1))
    expired_token = client.get("/api/users/me", headers={"Authorization": f"Bearer {expired}"})
    ok = client.get("/api/users/me", headers=alice["headers"])

    assert no_token.status_code == 401
    assert no_token.headers["WWW-Authenticate"] == "Bearer"
    assert bad_token.status_code == 401
    assert expired_token.status_code == 401
    assert ok.status_code == 200
    assert ok.json()["username"] == "alice"


def test_me_works_with_legacy_email_stored_in_db(client, db, make_user):
    """Regression: email đã lưu trong DB không được validate lại khi trả về.

    Trước đây UserOut.email dùng EmailStr -> user có email "@taskhub.local" (tên miền
    dành riêng, email-validator từ chối) làm GET /me trả về 500.
    """
    alice = make_user("alice")
    db.execute(update(User).where(User.id == alice["id"]).values(email="alice@taskhub.local"))
    db.commit()

    resp = client.get("/api/users/me", headers=alice["headers"])

    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@taskhub.local"


def test_update_me_including_password(client, make_user):
    alice = make_user("alice")

    resp = client.put(
        "/api/users/me",
        json={"full_name": "Alice Nguyen", "bio": "Backend dev", "password": "NewPassword456"},
        headers=alice["headers"],
    )

    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Alice Nguyen"
    assert resp.json()["bio"] == "Backend dev"
    old_login = client.post(
        "/api/users/login", data={"username": "alice", "password": DEFAULT_PASSWORD}
    )
    new_login = client.post(
        "/api/users/login", data={"username": "alice", "password": "NewPassword456"}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_update_me_with_taken_email_returns_409(client, make_user):
    make_user("alice")
    bob = make_user("bob")

    resp = client.put("/api/users/me", json={"email": "alice@example.com"}, headers=bob["headers"])

    assert resp.status_code == 409


def test_admin_only_endpoints(client, make_user):
    member = make_user("member")
    admin = make_user("boss", admin=True)

    assert client.get("/api/users", headers=member["headers"]).status_code == 403
    resp = client.get("/api/users", headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_deactivated_user_is_blocked(client, make_user):
    admin = make_user("boss", admin=True)
    bob = make_user("bob")

    resp = client.patch(f"/api/users/{bob['id']}", json={"is_active": False}, headers=admin["headers"])

    assert resp.status_code == 200
    # Token cũ vẫn còn hạn nhưng get_current_active_user chặn lại
    assert client.get("/api/users/me", headers=bob["headers"]).status_code == 403
    login = client.post("/api/users/login", data={"username": "bob", "password": DEFAULT_PASSWORD})
    assert login.status_code == 403


def test_admin_cannot_demote_themselves(client, make_user):
    admin = make_user("boss", admin=True)

    resp = client.patch(
        f"/api/users/{admin['id']}", json={"role": "member"}, headers=admin["headers"]
    )

    assert resp.status_code == 400
