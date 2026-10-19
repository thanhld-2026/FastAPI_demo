"""Băm mật khẩu (bcrypt) và tạo / giải mã JWT access token (PyJWT)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    """Băm mật khẩu bằng bcrypt. Salt ngẫu nhiên được nhúng sẵn trong chuỗi hash."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Mật khẩu > 72 bytes hoặc hash sai định dạng -> coi như sai mật khẩu
        return False


# Hash giả dùng khi username không tồn tại: vẫn chạy bcrypt để thời gian phản hồi
# tương đương trường hợp sai mật khẩu -> chống dò username bằng timing attack.
DUMMY_HASH = hash_password("dummy-password-for-timing-attack")


def create_access_token(subject: str | int, expires_delta: timedelta | None = None) -> str:
    """Tạo JWT. `sub` (subject) là user id; `exp` là thời điểm hết hạn."""
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(subject), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Giải mã + verify chữ ký + kiểm tra hạn (exp). Raise jwt.InvalidTokenError nếu không hợp lệ."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
