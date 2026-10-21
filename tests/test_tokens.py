"""Phụ lục feature 1: refresh token (rotation), logout."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app import crud
from app.config import settings
from app.models import RefreshToken
from app.security import hash_token
from tests.conftest import DEFAULT_PASSWORD

REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


def _refresh(client, refresh_token: str):
    return client.post(REFRESH_URL, json={"refresh_token": refresh_token})


# ---------- Login / refresh ----------
def test_login_returns_access_and_refresh_token(client, make_user):
    make_user("alice")

    resp = client.post(
        "/api/v1/auth/login", data={"username": "alice", "password": DEFAULT_PASSWORD}
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

    new_pair = resp.json()
    assert resp.status_code == 200
    assert new_pair["refresh_token"] != alice["refresh_token"]
    me = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {new_pair['access_token']}"}
    )
    assert me.json()["username"] == "alice"
    # Token mới dùng được, token cũ thì không (mỗi refresh token chỉ dùng 1 lần)
    assert _refresh(client, new_pair["refresh_token"]).status_code == 200


def test_reusing_a_rotated_refresh_token_revokes_all_sessions(client, make_user):
    """Token cũ (đã đổi sang token mới) bị gửi lại -> nghi bị lộ -> thu hồi mọi phiên."""
    alice = make_user("alice")
    old_token = alice["refresh_token"]
    new_token = _refresh(client, old_token).json()["refresh_token"]

    reused = _refresh(client, old_token)

    assert reused.status_code == 401
    # Phiên mới cũng bị thu hồi: kẻ gian giữ token mới cũng không dùng được nữa
    assert _refresh(client, new_token).status_code == 401


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


def test_refresh_for_deactivated_user_returns_403(client, make_user):
    admin = make_user("boss", admin=True)
    bob = make_user("bob")
    client.patch(f"/api/v1/users/{bob['id']}", json={"is_active": False}, headers=admin["headers"])

    assert _refresh(client, bob["refresh_token"]).status_code == 403


def test_revoke_succeeds_only_once(client, db, make_user):
    """2 request cùng dùng 1 refresh token đồng thời: chỉ 1 request thu hồi (và đổi) được."""
    alice = make_user("alice")
    token = crud.refresh_token.get_by_hash(db, hash_token(alice["refresh_token"]))
    assert token is not None

    first = crud.refresh_token.revoke(db, token)
    second = crud.refresh_token.revoke(db, token)
    db.commit()

    assert (first, second) == (True, False)


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
        "/api/v1/auth/login", data={"username": "alice", "password": DEFAULT_PASSWORD}
    ).json()

    client.post(LOGOUT_URL, json={"refresh_token": alice["refresh_token"]})

    assert _refresh(client, other_device["refresh_token"]).status_code == 200

