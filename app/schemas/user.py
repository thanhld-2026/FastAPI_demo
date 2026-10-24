from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field, StringConstraints, model_validator

from app.core import messages
from app.core.constants import (
    BIO_MAX_LENGTH,
    FULL_NAME_MAX_LENGTH,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN_LENGTH,
    REQUIRED_TEXT_MIN_LENGTH,
)
from app.models.enums import UserRole
from app.schemas.common import InputSchema, ORMSchema, reject_null_fields


def _check_bcrypt_limit(password: str) -> str:
    # bcrypt chỉ xử lý tối đa 72 BYTES (không phải 72 ký tự): ký tự tiếng Việt có dấu
    # chiếm 2-3 bytes nên phải kiểm tra theo bytes.
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(messages.PASSWORD_TOO_LONG.format(max_bytes=PASSWORD_MAX_BYTES))
    return password


Password = Annotated[
    str,
    # KHÔNG cắt khoảng trắng (InputSchema mặc định cắt): form login gửi nguyên văn, nếu lưu bản
    # đã cắt thì user đặt mật khẩu có dấu cách đầu / cuối sẽ không đăng nhập lại được
    StringConstraints(strip_whitespace=False),
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_BYTES),
    AfterValidator(_check_bcrypt_limit),
]


def _single_line_name(value: str) -> str:
    # Tên được đưa vào tiêu đề email (header): ký tự xuống dòng làm header không hợp lệ
    if "\n" in value or "\r" in value:
        raise ValueError(messages.FULL_NAME_MUST_BE_SINGLE_LINE)
    return value


FullName = Annotated[
    str,
    Field(min_length=REQUIRED_TEXT_MIN_LENGTH, max_length=FULL_NAME_MAX_LENGTH),
    AfterValidator(_single_line_name),
]


# ---------- Input ----------
class UserCreate(InputSchema):
    email: EmailStr = Field(examples=["alice@example.com"])
    password: Password = Field(examples=["Password123"])
    full_name: FullName = Field(examples=["Alice Nguyen"])


class UserUpdate(InputSchema):
    """PATCH /api/v1/users/me: chỉ cập nhật những field client gửi lên (exclude_unset).

    Không có `password`: đổi mật khẩu dùng endpoint riêng, bắt nhập mật khẩu hiện tại
    (gửi field lạ -> 422 nhờ extra="forbid").
    """

    email: EmailStr | None = None
    full_name: FullName | None = None
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)

    @model_validator(mode="after")
    def _reject_null_required(self):
        reject_null_fields(self, "email", "full_name")
        return self


class PasswordChange(InputSchema):
    # Mật khẩu hiện tại: không validate độ dài (chỉ so với hash đang lưu), không cắt khoảng trắng
    current_password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        examples=["Password123"]
    )
    new_password: Password = Field(examples=["NewPassword456"])

    @model_validator(mode="after")
    def _new_must_differ(self):
        if self.new_password == self.current_password:
            raise ValueError(messages.NEW_PASSWORD_SAME_AS_CURRENT)
        return self


class AdminUserUpdate(InputSchema):
    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _reject_null(self):
        reject_null_fields(self, "role", "is_active")
        return self


# ---------- Output ----------
class UserPublic(ORMSchema):
    """Thông tin công khai, dùng khi lồng (nested) trong project/task/comment."""

    id: int
    full_name: str


class UserOut(ORMSchema):
    """Thông tin đầy đủ của chính user (không bao giờ trả hashed_password)."""

    id: int
    email: str  # validate EmailStr khi NHẬN dữ liệu là đủ, không validate lại dữ liệu đã lưu
    full_name: str
    bio: str | None
    role: UserRole
    is_active: bool
    created_at: datetime

