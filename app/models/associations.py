"""Bảng trung gian cho quan hệ Many-to-Many.

Không cần class model riêng vì bảng chỉ chứa khóa ngoại (và created_at),
SQLAlchemy dùng chúng qua tham số `secondary=` của relationship().
"""

from sqlalchemy import Column, ForeignKey, Table, func

from app.database import Base
from app.models.base import UTCDateTime

# Task <-> Tag: 1 task có nhiều tag, 1 tag gắn cho nhiều task
task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True),
)

# User <-> Task (bookmark): 1 user bookmark nhiều task, 1 task được nhiều user bookmark
task_bookmarks = Table(
    "task_bookmarks",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("created_at", UTCDateTime(), server_default=func.now(), nullable=False),
)
