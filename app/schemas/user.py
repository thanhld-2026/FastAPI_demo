from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, model_validator

from app.models.enums import UserRole
from app.schemas.common import InputSchema, ORMSchema


def _check_bcrypt_limit(password: str) -> str:
    # bcrypt chỉ xử lý tối đa 72 BYTES (không phải 72 ký tự): ký tự tiếng Việt có dấu
    # chiếm 2-3 bytes nên phải kiểm tra theo bytes.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password is too long (max 72 bytes)")
    return password


Password = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_check_bcrypt_limit)]
Username = Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_]+$")]


# ---------- Input ----------
class UserCreate(InputSchema):
    username: Username = Field(examples=["alice"])
    email: EmailStr = Field(examples=["alice@example.com"])
    password: Password = Field(examples=["Password123"])
    full_name: str | None = Field(default=None, max_length=100, examples=["Alice Nguyen"])


class UserUpdate(InputSchema):
    """PUT /api/users/me: chỉ cập nhật những field client gửi lên (exclude_unset)."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=1000)
    password: Password | None = None

    @model_validator(mode="after")
    def _reject_null_required(self):
        for field in ("email", "password"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
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
