from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, model_validator

from app.core import messages
from app.core.constants import (
    BIO_MAX_LENGTH,
    FULL_NAME_MAX_LENGTH,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
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
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_BYTES),
    AfterValidator(_check_bcrypt_limit),
]
Username = Annotated[
    str,
    Field(
        min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, pattern=r"^[A-Za-z0-9_]+$"
    ),
]


# ---------- Input ----------
class UserCreate(InputSchema):
    username: Username = Field(examples=["alice"])
    email: EmailStr = Field(examples=["alice@example.com"])
    password: Password = Field(examples=["Password123"])
    full_name: str | None = Field(
        default=None, max_length=FULL_NAME_MAX_LENGTH, examples=["Alice Nguyen"]
    )


class UserUpdate(InputSchema):
    """PUT /api/users/me: chỉ cập nhật những field client gửi lên (exclude_unset)."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=FULL_NAME_MAX_LENGTH)
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    password: Password | None = None

    @model_validator(mode="after")
    def _reject_null_required(self):
        reject_null_fields(self, "email", "password")
        return self


class AdminUserUpdate(InputSchema):
    role: UserRole | None = None
    is_active: bool | None = None


# ---------- Output ----------
class UserPublic(ORMSchema):
    """Thông tin công khai, dùng khi lồng (nested) trong project/task/comment."""

    id: int
    username: str
    full_name: str | None


class UserOut(ORMSchema):
    """Thông tin đầy đủ của chính user (không bao giờ trả hashed_password)."""

    id: int
    username: str
    email: str  # validate EmailStr khi NHẬN dữ liệu là đủ, không validate lại dữ liệu đã lưu
    full_name: str | None
    bio: str | None
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
