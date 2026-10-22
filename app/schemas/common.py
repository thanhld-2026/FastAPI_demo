from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from app.core import messages
from app.core.constants import MAX_PAGE


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


@dataclass(frozen=True)
class PageParams:
    """Tham số phân trang đã validate (do dependency `Pagination` tạo ra)."""

    page: int  # bắt đầu từ 1
    limit: int

    @property
    def offset(self) -> int:
        """Số bản ghi bỏ qua ở tầng DB: trang 3, limit 5 -> bỏ qua 10 bản ghi đầu."""
        return (self.page - 1) * self.limit


class Page[T](BaseModel):
    """Response phân trang dùng chung: Page[TaskOut], Page[ProjectOut], ...

    - Không có dữ liệu: `pages` = 1 (trang 1 rỗng), FE không phải hiển thị "trang 1/0".
    - `page` lớn hơn `pages`: trả 200 với `items` rỗng (không coi là lỗi), FE dựa vào `pages`.
    - `pages` tối đa MAX_PAGE: dữ liệu quá sâu thì phải lọc thêm hoặc tăng `limit`.
    """

    items: list[T]
    total: int
    page: int
    limit: int
    pages: int  # tổng số trang, để FE hiển thị thanh phân trang

    @classmethod
    def build(cls, items: Sequence[Any], total: int, params: PageParams) -> Self:
        # items có thể là SQLAlchemy object, response_model (vd Page[TaskOut]) lọc field khi trả về
        return cls(
            items=list(items),
            total=total,
            page=params.page,
            limit=params.limit,
            # Chia làm tròn lên bằng số nguyên (không qua float); không vượt MAX_PAGE vì
            # query param page không nhận số lớn hơn (FE duyệt 1..pages sẽ không gặp 422)
            pages=min(MAX_PAGE, max(1, (total + params.limit - 1) // params.limit)),
        )


def reject_null_fields(schema: BaseModel, *fields: str) -> None:
    """Dùng cho schema partial update: field không gửi thì bỏ qua, nhưng gửi `null`
    cho field NOT NULL thì báo lỗi 422 (thay vì âm thầm bỏ qua hoặc ghi NULL xuống DB)."""
    for field in fields:
        if field in schema.model_fields_set and getattr(schema, field) is None:
            raise ValueError(messages.FIELD_CANNOT_BE_NULL.format(field=field))
