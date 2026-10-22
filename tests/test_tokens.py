"""Phụ lục feature 1-2: refresh token (rotation), logout, đổi mật khẩu."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app import crud
from app.config import settings
from app.models import RefreshToken, User
from app.security import hash_token
from tests.conftest import DEFAULT_PASSWORD

REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
PASSWORD_URL = "/api/v1/users/me/password"


def _refresh(client, refresh_token: str):
    return client.post(REFRESH_URL, json={"refresh_token": refresh_token})


# ---------- Login / refresh ----------
def test_login_returns_access_and_refresh_token(client, make_user):
    make_user("alice")

    resp = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": DEFAULT_PASSWORD}
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_refresh_token_is_stored_hashed(client, db, make_user):
    alice = make_user("alice")

    stored = db.scalars(select(RefreshToken.token_hash)).all()

    assert alice["refresh_token"] not in stored  # không lưu token gốc
    assert hash_token(alice["refresh_token"]) in stored


def test_refresh_rotates_the_refresh_token(client, make_user):
    alice = make_user("alice")

    resp = _refresh(client, alice["refresh_token"])
    old_again = _refresh(client, alice["refresh_token"])  # token cũ chỉ dùng được 1 lần

    new_pair = resp.json()
    assert resp.status_code == 200
    assert new_pair["refresh_token"] != alice["refresh_token"]
    assert old_again.status_code == 401
    me = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {new_pair['access_token']}"}
    )
    assert me.json()["full_name"] == "alice"
    # Dùng lại token cũ NGAY sau khi đổi (retry / 2 tab) nằm trong thời gian ân hạn:
    # chỉ trả 401, không coi là bị lộ -> token mới vẫn dùng được
    assert _refresh(client, new_pair["refresh_token"]).status_code == 200


def test_reusing_an_old_rotated_token_revokes_only_that_session(client, make_user, monkeypatch):
    """Token cũ bị gửi lại sau thời gian ân hạn -> nghi bị lộ -> thu hồi cả chuỗi của phiên đó.
    Phiên đăng nhập khác (thiết bị khác) không bị ảnh hưởng: kẻ gian giữ token cũ không thể
    đăng xuất user khỏi mọi nơi."""
    monkeypatch.setattr(settings, "REFRESH_TOKEN_REUSE_GRACE_SECONDS", 0)
    alice = make_user("alice")
    other_device = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": DEFAULT_PASSWORD}
    ).json()
    old_token = alice["refresh_token"]
    new_token = _refresh(client, old_token).json()["refresh_token"]

    reused = _refresh(client, old_token)

    assert reused.status_code == 401
    assert _refresh(client, new_token).status_code == 401  # cả chuỗi của phiên này bị thu hồi
    assert _refresh(client, other_device["refresh_token"]).status_code == 200


def test_unknown_or_expired_refresh_token_returns_401(client, db, make_user):
    alice = make_user("alice")
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(alice["refresh_token"]))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()

    assert _refresh(client, "not-a-real-token").status_code == 401
    assert _refresh(client, alice["refresh_token"]).status_code == 401
    assert client.post(REFRESH_URL, json={}).status_code == 422


def test_deactivating_a_user_ends_all_sessions(client, make_user):
    admin = make_user("boss", admin=True)
    bob = make_user("bob")
    url = f"/api/v1/users/{bob['id']}"

    client.patch(url, json={"is_active": False}, headers=admin["headers"])
    while_locked = _refresh(client, bob["refresh_token"])
    client.patch(url, json={"is_active": True}, headers=admin["headers"])
    after_unlock = _refresh(client, bob["refresh_token"])

    assert while_locked.status_code == 401
    # Mở khóa lại không làm sống lại phiên cũ (có thể chính là lý do bị khóa)
    assert after_unlock.status_code == 401


def test_revoke_succeeds_only_once(client, db, make_user):
    """2 request cùng dùng 1 refresh token đồng thời: chỉ 1 request thu hồi (và đổi) được."""
    alice = make_user("alice")
    token = crud.refresh_token.get_by_hash(db, hash_token(alice["refresh_token"]))
    assert token is not None

    first = crud.refresh_token.revoke(db, token)
    second = crud.refresh_token.revoke(db, token)
    db.commit()

    assert (first, second) == (True, False)


def test_refresh_losing_the_race_issues_no_token(client, db, make_user, monkeypatch):
    """Nhánh refresh() khi thu hồi thất bại (request khác vừa dùng token): 401 và token mới
    vừa tạo bị rollback, không lọt vào DB."""
    alice = make_user("alice")
    before = db.scalar(select(func.count()).select_from(RefreshToken))
    monkeypatch.setattr(crud.refresh_token, "revoke", lambda *args, **kwargs: False)

    resp = _refresh(client, alice["refresh_token"])

    db.expire_all()
    assert resp.status_code == 401
    assert db.scalar(select(func.count()).select_from(RefreshToken)) == before


# ---------- Logout ----------
def test_logout_revokes_refresh_token_and_is_idempotent(client, make_user):
    alice = make_user("alice")
    body = {"refresh_token": alice["refresh_token"]}

    first = client.post(LOGOUT_URL, json=body)
    again = client.post(LOGOUT_URL, json=body)
    unknown = client.post(LOGOUT_URL, json={"refresh_token": "not-a-real-token"})

    assert (first.status_code, again.status_code, unknown.status_code) == (204, 204, 204)
    assert _refresh(client, alice["refresh_token"]).status_code == 401


def test_logout_only_ends_that_session(client, make_user):
    alice = make_user("alice")
    other_device = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": DEFAULT_PASSWORD}
    ).json()

    client.post(LOGOUT_URL, json={"refresh_token": alice["refresh_token"]})

    assert _refresh(client, other_device["refresh_token"]).status_code == 200


def test_logout_with_an_old_token_ends_the_current_session(client, make_user):
    """User bấm logout bằng token cũ (đã bị đổi sang token mới, có thể ở trong tay kẻ gian):
    token mới của phiên đó cũng phải mất hiệu lực."""
    alice = make_user("alice")
    new_token = _refresh(client, alice["refresh_token"]).json()["refresh_token"]

    resp = client.post(LOGOUT_URL, json={"refresh_token": alice["refresh_token"]})

    assert resp.status_code == 204
    assert _refresh(client, new_token).status_code == 401


# ---------- Đổi mật khẩu ----------
def test_change_password(client, make_user):
    alice = make_user("alice")
    other_device = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": DEFAULT_PASSWORD}
    ).json()

    resp = client.put(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "NewPassword456"},
        headers=alice["headers"],
    )

    assert resp.status_code == 200
    old_login = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": DEFAULT_PASSWORD}
    )
    new_login = client.post(
        "/api/v1/auth/login", data={"username": "alice@example.com", "password": "NewPassword456"}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    # Mọi phiên cũ bị đăng xuất, thiết bị hiện tại dùng cặp token mới trả về
    assert _refresh(client, alice["refresh_token"]).status_code == 401
    assert _refresh(client, other_device["refresh_token"]).status_code == 401
    assert _refresh(client, resp.json()["refresh_token"]).status_code == 200


def test_password_whitespace_is_kept(client, make_user):
    """Không cắt khoảng trắng của mật khẩu: form login gửi nguyên văn."""
    alice = make_user("alice")
    spaced = "  NewPassword456  "

    client.put(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": spaced},
        headers=alice["headers"],
    )

    login = "/api/v1/auth/login"
    exact = client.post(login, data={"username": alice["email"], "password": spaced})
    assert exact.status_code == 200
    trimmed = client.post(login, data={"username": alice["email"], "password": spaced.strip()})
    assert trimmed.status_code == 401


def test_change_password_validation(client, db, make_user):
    alice = make_user("alice")
    old_hash = db.scalar(select(User.hashed_password).where(User.id == alice["id"]))

    wrong_current = client.put(
        PASSWORD_URL,
        json={"current_password": "WrongPass1", "new_password": "NewPassword456"},
        headers=alice["headers"],
    )
    same_as_current = client.put(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
        headers=alice["headers"],
    )
    too_short = client.put(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
        headers=alice["headers"],
    )
    anonymous = client.put(
        PASSWORD_URL, json={"current_password": DEFAULT_PASSWORD, "new_password": "NewPassword456"}
    )

    assert wrong_current.status_code == 400  # không phải 401: phiên đăng nhập vẫn hợp lệ
    assert same_as_current.status_code == 422
    assert too_short.status_code == 422
    assert anonymous.status_code == 401
    db.expire_all()
    assert db.scalar(select(User.hashed_password).where(User.id == alice["id"])) == old_hash
    assert _refresh(client, alice["refresh_token"]).status_code == 200  # phiên vẫn còn
