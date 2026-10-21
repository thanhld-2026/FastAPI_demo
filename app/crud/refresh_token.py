"""Truy cập bảng refresh_tokens.

Các hàm ghi ở đây cố ý KHÔNG commit: service (services/auth.py) gom nhiều thao tác
(thu hồi token cũ + tạo token mới, đổi mật khẩu + thu hồi mọi phiên) vào 1 lần commit.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken


def add(db: Session, *, user_id: int, token_hash: str, expires_at: datetime) -> RefreshToken:
    token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(token)
    return token


def get_by_hash(db: Session, token_hash: str) -> RefreshToken | None:
    return db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))


def revoke(db: Session, token: RefreshToken, *, replaced_by_id: int | None = None) -> bool:
    """Thu hồi 1 token. Trả về False nếu token đã bị thu hồi trước đó.

    Dùng UPDATE có điều kiện `revoked_at IS NULL` thay vì đọc rồi ghi: 2 request cùng dùng
    1 refresh token đồng thời thì chỉ 1 request thu hồi được (UPDATE trả về đúng 1 dòng),
    request còn lại nhận False -> không thể đổi 1 token lấy 2 token mới.
    """
    revoked_id = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), replaced_by_id=replaced_by_id)
        .returning(RefreshToken.id)
    ).scalar_one_or_none()
    return revoked_id is not None


def revoke_all_for_user(db: Session, user_id: int) -> None:
    """Thu hồi mọi phiên đăng nhập còn hiệu lực của user (đổi mật khẩu, nghi token bị lộ)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
