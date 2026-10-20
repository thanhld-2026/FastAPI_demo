from pydantic import Field, field_validator

from app.core.constants import TAG_NAME_MAX_LENGTH
from app.schemas.common import InputSchema, ORMSchema


class TagCreate(InputSchema):
    name: str = Field(
        min_length=1, max_length=TAG_NAME_MAX_LENGTH, pattern=r"^[a-z0-9-]+$", examples=["backend"]
    )

    @field_validator("name", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        # "  Backend " -> "backend": tránh tạo tag trùng chỉ khác hoa/thường
        return value.strip().lower() if isinstance(value, str) else value


class TagOut(ORMSchema):
    id: int
    name: str
