from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import InputSchema, ORMSchema
from app.schemas.tag import TagOut
from app.schemas.user import UserPublic

# [1, 2, 2] -> [1, 2]: bỏ id trùng nhưng giữ nguyên thứ tự
TagIds = Annotated[list[int], AfterValidator(lambda ids: list(dict.fromkeys(ids)))]


# ---------- Input ----------
class TaskCreate(InputSchema):
    title: str = Field(min_length=1, max_length=200, examples=["Thiết kế database"])
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    tag_ids: TagIds = Field(default_factory=list, examples=[[1, 2]])


class TaskUpdate(InputSchema):
    """Partial update: chỉ field nào gửi lên mới được cập nhật."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    tag_ids: TagIds | None = None

    @model_validator(mode="after")
    def _reject_null_required(self):
        # description/due_date được phép null (xóa giá trị), còn các field NOT NULL thì không
        for field in ("title", "status", "priority", "tag_ids"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


# ---------- Output ----------
class TaskBrief(ORMSchema):
    """Dạng rút gọn, dùng khi lồng trong Project / Profile."""

    id: int
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    assignee: UserPublic | None


class TaskOut(ORMSchema):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    project_id: int
    creator: UserPublic
    assignee: UserPublic | None
    tags: list[TagOut]
    created_at: datetime
    updated_at: datetime


class BookmarkOut(ORMSchema):
    task_id: int
    bookmarked: bool
