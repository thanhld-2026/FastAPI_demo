"""Nghiệp vụ xác thực: đăng nhập, refresh token (rotation), logout, đổi mật khẩu.

Access token (JWT, 15 phút): không lưu DB, không thu hồi được -> để sống ngắn.
Refresh token (chuỗi ngẫu nhiên, 7 ngày): lưu hash trong DB -> thu hồi được khi logout /
đổi mật khẩu. Mỗi refresh token chỉ dùng được 1 lần: refresh xong thì token cũ bị thu hồi và
trỏ sang token mới (rotation).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.core import messages
from app.core.exceptions import BadRequestException, ForbiddenException, UnauthorizedException
from app.models import RefreshToken, User
from app.schemas.auth import TokenPair
from app.schemas.user import PasswordChange
from app.security import create_access_token, create_refresh_token, hash_token, verify_password


def _as_utc(value: datetime) -> datetime:
    # SQLite (dùng khi test) không lưu timezone -> đọc ra datetime "naive", vốn được ghi bằng UTC
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_expired(token: RefreshToken) -> bool:
    return _as_utc(token.expires_at) <= datetime.now(UTC)


def _new_token_pair(db: Session, user: User) -> tuple[TokenPair, RefreshToken]:
    """Tạo cặp token mới, refresh token được thêm vào session (chưa commit)."""
    raw_refresh = create_refresh_token()
    stored = crud.refresh_token.add(
        db,
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    pair = TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=raw_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return pair, stored


def login(db: Session, identifier: str, password: str) -> TokenPair:
    user = crud.user.authenticate(db, identifier, password)
    if user is None:
        raise UnauthorizedException(messages.INCORRECT_LOGIN)
    if not user.is_active:
        raise ForbiddenException(messages.INACTIVE_USER)
    pair, _ = _new_token_pair(db, user)
    db.commit()
    return pair


def refresh(db: Session, raw_refresh: str) -> TokenPair:
    token = crud.refresh_token.get_by_hash(db, hash_token(raw_refresh))
    if token is None or _is_expired(token):
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)

    if token.revoked_at is not None:
        if token.replaced_by_id is not None:
            # Token đã được đổi sang token mới mà vẫn bị gửi lên lần nữa: rất có thể token
            # bị lộ (kẻ gian và user cùng giữ 1 token). Thu hồi mọi phiên để buộc đăng nhập lại.
            # Phải commit trước khi raise, vì lỗi sẽ làm get_db rollback session.
            crud.refresh_token.revoke_all_for_user(db, token.user_id)
            db.commit()
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)

    if not token.user.is_active:
        raise ForbiddenException(messages.INACTIVE_USER)

    pair, new_token = _new_token_pair(db, token.user)
    db.flush()  # có new_token.id để token cũ trỏ sang
    if not crud.refresh_token.revoke(db, token, replaced_by_id=new_token.id):
        # Request khác vừa dùng đúng token này: raise -> get_db rollback, token mới bị hủy
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)
    db.commit()  # thu hồi token cũ + lưu token mới trong cùng 1 transaction
    return pair


def logout(db: Session, raw_refresh: str) -> None:
    """Idempotent: token không tồn tại / đã thu hồi cũng không báo lỗi (không lộ thông tin gì)."""
    token = crud.refresh_token.get_by_hash(db, hash_token(raw_refresh))
    if token is not None and token.revoked_at is None:
        crud.refresh_token.revoke(db, token)
        db.commit()


def change_password(db: Session, user: User, data: PasswordChange) -> None:
    """Đổi mật khẩu + thu hồi mọi refresh token của user (đăng xuất mọi thiết bị) trong 1 commit.

    Access token đang dùng vẫn sống tới khi hết hạn (tối đa ACCESS_TOKEN_EXPIRE_MINUTES).
    """
    if not verify_password(data.current_password, user.hashed_password):
        # 400 chứ không phải 401: user vẫn đăng nhập hợp lệ, chỉ nhập sai mật khẩu cũ
        # (401 sẽ khiến FE tưởng phiên hết hạn và đẩy về màn login)
        raise BadRequestException(messages.WRONG_CURRENT_PASSWORD)
    crud.user.set_password(user, data.new_password)
    crud.refresh_token.revoke_all_for_user(db, user.id)
    db.commit()
