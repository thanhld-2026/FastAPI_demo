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


def _is_expired(token: RefreshToken) -> bool:
    return token.expires_at <= datetime.now(UTC)


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


def _lock_user(db: Session, user_id: int) -> User:
    """Khóa dòng user: refresh / logout / đổi mật khẩu / khóa tài khoản của cùng 1 user chạy
    tuần tự. Nếu không, đổi mật khẩu có thể không thấy token vừa được 1 refresh khác tạo ra
    (chưa commit) và token đó sống sót sau khi đổi mật khẩu."""
    user = crud.user.get_for_update(db, user_id)
    if user is None:  # user bị xóa
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)
    return user


def _rotated_recently(token: RefreshToken) -> bool:
    grace = timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
    return token.revoked_at is not None and datetime.now(UTC) - token.revoked_at <= grace


def login(db: Session, email: str, password: str) -> TokenPair:
    user = crud.user.authenticate(db, email, password)
    if user is None:
        raise UnauthorizedException(messages.INCORRECT_LOGIN)
    if not user.is_active:
        raise ForbiddenException(messages.INACTIVE_USER)
    pair, _ = _new_token_pair(db, user)
    db.commit()
    return pair


def refresh(db: Session, raw_refresh: str) -> TokenPair:
    token_hash = hash_token(raw_refresh)
    token = crud.refresh_token.get_by_hash(db, token_hash)
    if token is None or _is_expired(token):
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)
    user = _lock_user(db, token.user_id)
    token = crud.refresh_token.get_by_hash(db, token_hash)  # đọc lại sau khi có khóa
    assert token is not None

    if token.revoked_at is not None:
        if token.replaced_by_id is not None and not _rotated_recently(token):
            # Token đã đổi sang token mới từ lâu mà vẫn bị gửi lại: rất có thể bị lộ (kẻ gian và
            # user cùng giữ 1 token) -> thu hồi cả chuỗi của phiên này (kể cả token mới nhất).
            # Commit trước khi raise, vì lỗi sẽ làm get_db rollback session.
            crud.refresh_token.revoke_chain(db, token)
            db.commit()
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)

    if not user.is_active:
        raise ForbiddenException(messages.INACTIVE_USER)

    pair, new_token = _new_token_pair(db, user)
    db.flush()  # có new_token.id để token cũ trỏ sang
    if not crud.refresh_token.revoke(db, token, replaced_by_id=new_token.id):
        # Phòng hờ (đã có khóa user nên hiếm khi xảy ra): token vừa bị dùng ở request khác
        raise UnauthorizedException(messages.INVALID_REFRESH_TOKEN)
    db.commit()  # thu hồi token cũ + lưu token mới trong cùng 1 transaction
    return pair


def logout(db: Session, raw_refresh: str) -> None:
    """Kết thúc phiên đăng nhập của refresh token này. Idempotent: token không tồn tại / đã thu
    hồi cũng trả 204 (không lộ thông tin gì).

    Token cũ đã được đổi sang token mới vẫn kết thúc được phiên (thu hồi cả chuỗi): user bấm
    logout bằng token cũ thì token mới (có thể đang nằm trong tay kẻ gian) cũng mất hiệu lực.
    """
    token = crud.refresh_token.get_by_hash(db, hash_token(raw_refresh))
    if token is None:
        return
    _lock_user(db, token.user_id)
    crud.refresh_token.revoke_chain(db, token)
    db.commit()


def revoke_all_sessions(db: Session, user_id: int) -> None:
    """Thu hồi mọi refresh token của user (KHÔNG commit), dùng khi khóa tài khoản."""
    _lock_user(db, user_id)
    crud.refresh_token.revoke_all_for_user(db, user_id)


def change_password(db: Session, user: User, data: PasswordChange) -> TokenPair:
    """Đổi mật khẩu + thu hồi mọi phiên đăng nhập + cấp cặp token mới cho thiết bị hiện tại,
    tất cả trong 1 commit. Các thiết bị khác phải đăng nhập lại.

    Access token đang dùng ở thiết bị khác vẫn sống tới khi hết hạn (tối đa
    ACCESS_TOKEN_EXPIRE_MINUTES).
    """
    user = _lock_user(db, user.id)
    if not verify_password(data.current_password, user.hashed_password):
        # 400 chứ không phải 401: user vẫn đăng nhập hợp lệ, chỉ nhập sai mật khẩu cũ
        # (401 sẽ khiến FE tưởng phiên hết hạn và đẩy về màn login)
        raise BadRequestException(messages.WRONG_CURRENT_PASSWORD)
    crud.user.set_password(user, data.new_password)
    crud.refresh_token.revoke_all_for_user(db, user.id)
    pair, _ = _new_token_pair(db, user)
    db.commit()
    return pair
