"""Mixin và helper dùng chung cho các model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Thêm created_at / updated_at; giá trị do DB tự sinh (server_default)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
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
