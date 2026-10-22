"""Bảng trung gian cho quan hệ Many-to-Many.

Không cần class model riêng vì bảng chỉ chứa khóa ngoại (và created_at),
SQLAlchemy dùng chúng qua tham số `secondary=` của relationship().
"""

from sqlalchemy import Column, ForeignKey, Table, func

from app.database import Base
from app.models.base import UTCDateTime

# Task <-> Label: 1 task có nhiều label, 1 label gắn cho nhiều task (cùng project)
# Giới hạn đã biết: "label phải cùng project với task" chỉ được kiểm tra trong code
# (get_labels_by_ids, set_task_label), DB không chặn. Muốn DB chặn thì thêm cột project_id vào
# task_labels + khóa ngoại kép (task_id, project_id) -> tasks, (label_id, project_id) -> labels.
task_labels = Table(
    "task_labels",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True, index=True),
)

# User <-> Task (bookmark): 1 user bookmark nhiều task, 1 task được nhiều user bookmark
task_bookmarks = Table(
    "task_bookmarks",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("created_at", UTCDateTime(), server_default=func.now(), nullable=False),
)
