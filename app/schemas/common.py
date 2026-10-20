from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.core import messages

T = TypeVar("T")


class InputSchema(BaseModel):
    """Base cho dữ liệu client gửi lên (request body).

    - str_strip_whitespace: tự cắt khoảng trắng đầu/cuối chuỗi.
    - extra="forbid": gửi field lạ -> 422. Chặn "mass assignment", ví dụ client
      cố gửi {"role": "admin"} khi đăng ký sẽ bị từ chối thay vì bị bỏ qua âm thầm.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ORMSchema(BaseModel):
    """Base cho dữ liệu trả về: from_attributes=True cho phép đọc thẳng từ SQLAlchemy object."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Response phân trang dùng chung: Page[TaskOut], Page[ProjectOut], ..."""

    items: list[T]
    total: int
    skip: int
    limit: int


def reject_null_fields(schema: BaseModel, *fields: str) -> None:
    """Dùng cho schema partial update: field không gửi thì bỏ qua, nhưng gửi `null`
    cho field NOT NULL thì báo lỗi 422 (thay vì âm thầm bỏ qua hoặc ghi NULL xuống DB)."""
    for field in fields:
        if field in schema.model_fields_set and getattr(schema, field) is None:
            raise ValueError(messages.FIELD_CANNOT_BE_NULL.format(field=field))
