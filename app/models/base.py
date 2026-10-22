"""Mixin và helper dùng chung cho các model."""

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, Enum, TypeDecorator, func
from sqlalchemy.orm import Mapped, mapped_column


class UTCDateTime(TypeDecorator[datetime]):
    """Cột DateTime có timezone, đọc ra LUÔN là datetime có tzinfo (UTC).

    PostgreSQL trả về datetime có timezone, nhưng SQLite (dùng khi test) không lưu timezone nên
    trả về datetime "naive". So sánh naive với aware ném TypeError -> xử lý 1 lần ở kiểu cột
    thay vì rải hàm chuyển đổi ở từng chỗ so sánh thời gian.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class TimestampMixin:
    """Thêm created_at / updated_at; giá trị do DB tự sinh (server_default)."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )


def enum_column(enum_cls: type[enum.Enum]) -> Enum:
    """Lưu Enum dưới dạng VARCHAR (native_enum=False) với giá trị là `.value`.

    Không dùng kiểu ENUM native của PostgreSQL vì mỗi lần thêm giá trị mới phải
    ALTER TYPE -> migration phức tạp hơn. Việc validate giá trị đã do Pydantic lo.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [member.value for member in e],
        validate_strings=True,
    )
