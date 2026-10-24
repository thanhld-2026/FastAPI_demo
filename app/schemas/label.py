from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    DEFAULT_LABEL_COLOR,
    LABEL_COLOR_PATTERN,
    LABEL_NAME_MAX_LENGTH,
    LABEL_NAME_PATTERN,
    REQUIRED_TEXT_MIN_LENGTH,
)
from app.schemas.common import InputSchema, ORMSchema, reject_null_fields


class _LabelNormalizeMixin:
    @field_validator("name", "color", mode="before", check_fields=False)
    @classmethod
    def _lowercase(cls, value: object) -> object:
        # mode="before": chạy TRƯỚC các ràng buộc của Field (pattern, độ dài) -> "Bug" thành "bug"
        # rồi mới so với LABEL_NAME_PATTERN (chạy sau thì "Bug" bị 422 vì có chữ hoa).
        # "Bug" / "bug", "#EF4444" / "#ef4444" là 1 -> UNIQUE (project_id, name) chặn được trùng.
        # Khoảng trắng 2 đầu do InputSchema cắt sau bước này.
        return value.lower() if isinstance(value, str) else value


class LabelCreate(_LabelNormalizeMixin, InputSchema):
    name: str = Field(
        min_length=REQUIRED_TEXT_MIN_LENGTH,
        max_length=LABEL_NAME_MAX_LENGTH,
        pattern=LABEL_NAME_PATTERN,
        examples=["bug"],
    )
    color: str = Field(
        default=DEFAULT_LABEL_COLOR, pattern=LABEL_COLOR_PATTERN, examples=["#ef4444"]
    )


class LabelUpdate(_LabelNormalizeMixin, InputSchema):
    name: str | None = Field(
        default=None,
        min_length=REQUIRED_TEXT_MIN_LENGTH,
        max_length=LABEL_NAME_MAX_LENGTH,
        pattern=LABEL_NAME_PATTERN,
    )
    color: str | None = Field(default=None, pattern=LABEL_COLOR_PATTERN)

    @model_validator(mode="after")
    def _reject_null_required(self):
        reject_null_fields(self, "name", "color")
        return self


class LabelOut(ORMSchema):
    id: int
    project_id: int
    name: str
    color: str
