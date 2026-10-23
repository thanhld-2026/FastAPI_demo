"""Mục 4 & 5: Đăng ký / đăng nhập JWT, bảo vệ endpoint, phân quyền admin."""

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import update

from app import crud
from app.config import settings
from app.models import User
from app.security import create_access_token
from tests.conftest import DEFAULT_PASSWORD


def test_register_returns_user_without_password(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"full_name": "alice", "email": "Alice@Example.com", "password": DEFAULT_PASSWORD},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "alice"
    assert body["email"] == "alice@example.com"  # email được chuẩn hóa chữ thường
    assert body["role"] == "member"
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email_returns_409(client, make_user):
    make_user("alice")

    same_name = client.post(
        "/api/v1/auth/register",
        json={"full_name": "alice", "email": "other@example.com", "password": DEFAULT_PASSWORD},
    )
    same_email = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Alice 2", "email": "ALICE@example.com", "password": DEFAULT_PASSWORD},
    )

    assert same_name.status_code == 201  # tên hiển thị được phép trùng
    assert same_email.status_code == 409  # email so sánh không phân biệt hoa thường


def test_register_rejects_mass_assignment_of_role(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "hacker",
            "email": "hacker@example.com",
            "password": DEFAULT_PASSWORD,
            "role": "admin",
        },
    )
    assert resp.status_code == 422


def test_register_validates_input(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"full_name": "", "email": "not-an-email", "password": "short"},
    )

    assert resp.status_code == 422
    invalid_fields = {err["loc"][-1] for err in resp.json()["detail"]}
    assert invalid_fields == {"full_name", "email", "password"}


def test_login_with_email(client, make_user):
    make_user("alice")

    # Form OAuth2 bắt buộc tên field `username`, giá trị là email (không phân biệt hoa thường)
    by_email = client.post(
        "/api/v1/auth/login", data={"username": "Alice@Example.com", "password": DEFAULT_PASSWORD}
    )
    by_name = client.post(
        "/api/v1/auth/login", data={"username": "alice", "password": DEFAULT_PASSWORD}
    )

    assert by_email.status_code == 200
    assert by_email.json()["token_type"] == "bearer"
    assert by_name.status_code == 401  # không còn đăng nhập bằng username


def test_login_with_wrong_password_returns_401(client, make_user):
    make_user("alice")

    resp = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": "WrongPass1"}
    )
    unknown = client.post(
        "/api/v1/auth/login", data={"username": "nobody@example.com", "password": "WrongPass1"}
    )

    assert resp.status_code == 401
    assert unknown.status_code == 401  # không tiết lộ email có tồn tại hay không


def test_me_requires_valid_token(client, make_user):
    alice = make_user("alice")

    no_token = client.get("/api/v1/users/me")
    bad_token = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    expired = create_access_token(alice["id"], expires_delta=timedelta(seconds=-1))
    expired_token = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    ok = client.get("/api/v1/users/me", headers=alice["headers"])

    assert no_token.status_code == 401
    assert no_token.headers["WWW-Authenticate"] == "Bearer"
    assert bad_token.status_code == 401
    assert expired_token.status_code == 401
    assert ok.status_code == 200
    assert ok.json()["full_name"] == "alice"


def test_only_access_tokens_are_accepted(client, make_user):
    """JWT khác ký cùng SECRET_KEY (vd token đặt lại mật khẩu sau này) không dùng thay access
    token được: thiếu claim `type` hoặc `type` khác "access" -> 401."""
    alice = make_user("alice")
    now = datetime.now(UTC)
    base = {"sub": str(alice["id"]), "iat": now, "exp": now + timedelta(minutes=5)}

    def call(payload: dict) -> int:
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}
        return client.get("/api/v1/users/me", headers=headers).status_code

    assert call({**base, "type": "access"}) == 200
    assert call({**base, "type": "reset_password"}) == 401
    assert call(base) == 401  # token cũ chưa có `type`


def test_me_works_with_legacy_email_stored_in_db(client, db, make_user):
    """Regression: email đã lưu trong DB không được validate lại khi trả về.

    Trước đây UserOut.email dùng EmailStr -> user có email "@taskhub.local" (tên miền
    dành riêng, email-validator từ chối) làm GET /me trả về 500.
    """
    alice = make_user("alice")
    db.execute(update(User).where(User.id == alice["id"]).values(email="alice@taskhub.local"))
    db.commit()

    resp = client.get("/api/v1/users/me", headers=alice["headers"])

    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@taskhub.local"


def test_patch_me_updates_only_sent_fields(client, make_user):
    alice = make_user("alice")
    url = "/api/v1/users/me"

    first = client.patch(url, json={"full_name": "Alice Nguyen"}, headers=alice["headers"])
    second = client.patch(url, json={"bio": "Backend dev"}, headers=alice["headers"])

    assert first.status_code == 200
    assert second.json()["full_name"] == "Alice Nguyen"  # field không gửi giữ nguyên
    assert second.json()["bio"] == "Backend dev"


def test_patch_me_cannot_change_password(client, make_user):
    alice = make_user("alice")

    resp = client.patch(
        "/api/v1/users/me", json={"password": "NewPassword456"}, headers=alice["headers"]
    )

    assert resp.status_code == 422  # phải dùng PUT /users/me/password


def test_update_me_with_taken_email_returns_409(client, make_user):
    make_user("alice")
    bob = make_user("bob")

    resp = client.patch(
        "/api/v1/users/me", json={"email": "alice@example.com"}, headers=bob["headers"]
    )

    assert resp.status_code == 409


def test_admin_only_endpoints(client, make_user):
    member = make_user("member")
    admin = make_user("boss", admin=True)

    assert client.get("/api/v1/users", headers=member["headers"]).status_code == 403
    resp = client.get("/api/v1/users", headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_deactivated_user_is_blocked(client, make_user):
    admin = make_user("boss", admin=True)
    bob = make_user("bob")

    resp = client.patch(
        f"/api/v1/users/{bob['id']}", json={"is_active": False}, headers=admin["headers"]
    )

    assert resp.status_code == 200
    # Token cũ vẫn còn hạn nhưng get_current_active_user chặn lại
    assert client.get("/api/v1/users/me", headers=bob["headers"]).status_code == 403
    login = client.post(
        "/api/v1/auth/login", data={"username": "bob@example.com", "password": DEFAULT_PASSWORD}
    )
    assert login.status_code == 403


def test_admin_cannot_demote_themselves(client, make_user):
    admin = make_user("boss", admin=True)

    resp = client.patch(
        f"/api/v1/users/{admin['id']}", json={"role": "member"}, headers=admin["headers"]
    )

    assert resp.status_code == 400


def test_update_me_email_race_condition_returns_409(client, make_user, monkeypatch):
    """2 request đổi sang cùng 1 email đồng thời: cả 2 đều qua bước check trước,
    UNIQUE constraint trong DB phải chặn request sau -> 409 chứ không phải 500."""
    make_user("alice")
    bob = make_user("bob")
    # Giả lập request còn lại chưa kịp commit lúc bob check email
    monkeypatch.setattr(crud.user, "get_by_email", lambda db, email: None)

    resp = client.patch(
        "/api/v1/users/me", json={"email": "alice@example.com"}, headers=bob["headers"]
    )

    assert resp.status_code == 409


def test_admin_update_rejects_null_values(client, make_user):
    admin = make_user("boss", admin=True)
    bob = make_user("bob")
    url = f"/api/v1/users/{bob['id']}"

    assert client.patch(url, json={"role": None}, headers=admin["headers"]).status_code == 422
    assert client.patch(url, json={"is_active": None}, headers=admin["headers"]).status_code == 422


def test_admin_cannot_deactivate_themselves(client, make_user):
    admin = make_user("boss", admin=True)

    resp = client.patch(
        f"/api/v1/users/{admin['id']}", json={"is_active": False}, headers=admin["headers"]
    )

    assert resp.status_code == 400
