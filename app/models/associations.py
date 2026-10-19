"""Bảng trung gian cho quan hệ Many-to-Many.

Không cần class model riêng vì bảng chỉ chứa khóa ngoại,
SQLAlchemy dùng chúng qua tham số `secondary=` của relationship().
"""

from sqlalchemy import Column, ForeignKey, Table

from app.database import Base

# Task <-> Tag: 1 task có nhiều tag, 1 tag gắn cho nhiều task
task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True),
)
