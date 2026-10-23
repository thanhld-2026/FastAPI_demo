from pydantic import Field, field_validator

from app.core.constants import REQUIRED_TEXT_MIN_LENGTH, TAG_NAME_MAX_LENGTH
from app.schemas.common import InputSchema, ORMSchema


class TagCreate(InputSchema):
    name: str = Field(
        min_length=REQUIRED_TEXT_MIN_LENGTH,
        max_length=TAG_NAME_MAX_LENGTH,
        pattern=r"^[a-z0-9-]+$",
        examples=["backend"],
    )

    @field_validator("name", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        # "  Backend " -> "backend": tránh tạo tag trùng chỉ khác hoa/thường
        return value.strip().lower() if isinstance(value, str) else value


class TagOut(ORMSchema):
    id: int
    name: str
