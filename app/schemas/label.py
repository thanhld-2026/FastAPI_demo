from pydantic import Field, field_validator, model_validator

from app.core.constants import DEFAULT_LABEL_COLOR, LABEL_COLOR_PATTERN, LABEL_NAME_MAX_LENGTH
from app.schemas.common import InputSchema, ORMSchema, reject_null_fields


class _LabelColorMixin:
    @field_validator("name", "color", check_fields=False)
    @classmethod
    def _lowercase(cls, value: str | None) -> str | None:
        # "Bug" / "bug", "#EF4444" / "#ef4444" là 1 -> lưu 1 dạng (khoảng trắng 2 đầu đã được
        # InputSchema cắt), để UNIQUE (project_id, name) chặn được trùng tên khác hoa thường
        return value.lower() if value is not None else None


class LabelCreate(_LabelColorMixin, InputSchema):
    name: str = Field(min_length=1, max_length=LABEL_NAME_MAX_LENGTH, examples=["bug"])
    color: str = Field(
        default=DEFAULT_LABEL_COLOR, pattern=LABEL_COLOR_PATTERN, examples=["#ef4444"]
    )


class LabelUpdate(_LabelColorMixin, InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=LABEL_NAME_MAX_LENGTH)
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
