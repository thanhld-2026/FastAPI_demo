from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import TOKEN_HASH_LENGTH
from app.database import Base
from app.models.base import UTCDateTime

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """Mỗi dòng là 1 phiên đăng nhập (1 refresh token). Token gốc không được lưu, chỉ lưu hash.

    - revoked_at: thời điểm bị thu hồi (logout, đổi mật khẩu, hoặc đã được đổi sang token mới).
    - replaced_by_id: token mới được cấp khi refresh (rotation). Các token nối nhau qua cột này
      thành 1 chuỗi = 1 phiên đăng nhập trên 1 thiết bị. Token đã có replaced_by_id mà vẫn bị gửi
      lên lần nữa -> dấu hiệu token bị lộ -> thu hồi cả chuỗi (xem services/auth.py).
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    # CASCADE: token chỉ là phiên đăng nhập, xóa user thì xóa luôn (khác activity là dữ liệu audit)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # index: xóa 1 token thì DB phải tìm các dòng trỏ tới nó để SET NULL (không index -> quét bảng)
    replaced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    user: Mapped[User] = relationship()
