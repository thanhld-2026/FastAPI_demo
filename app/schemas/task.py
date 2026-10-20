from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, PositiveInt, model_validator

from app.core import messages
from app.core.constants import TASK_TITLE_MAX_LENGTH
from app.models.enums import ActivityAction, TaskPriority, TaskStatus
from app.schemas.common import InputSchema, ORMSchema, reject_null_fields
from app.schemas.tag import TagOut
from app.schemas.user import UserPublic

# [1, 2, 2] -> [1, 2]: bỏ id trùng nhưng giữ nguyên thứ tự
TagIds = Annotated[list[int], AfterValidator(lambda ids: list(dict.fromkeys(ids)))]


def _not_in_past(value: date | None) -> date | None:
    # Chỉ validate khi client có gửi due_date -> task đã quá hạn vẫn sửa được các field khác
    if value is not None and value < date.today():
        raise ValueError(messages.DUE_DATE_IN_PAST)
    return value


DueDate = Annotated[date | None, AfterValidator(_not_in_past)]


# ---------- Input ----------
class TaskCreate(InputSchema):
    title: str = Field(
        min_length=1, max_length=TASK_TITLE_MAX_LENGTH, examples=["Thiết kế database"]
    )
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: DueDate = None
    tag_ids: TagIds = Field(default_factory=list, examples=[[1, 2]])


class TaskUpdate(InputSchema):
    """Partial update: chỉ field nào gửi lên mới được cập nhật."""

    title: str | None = Field(default=None, min_length=1, max_length=TASK_TITLE_MAX_LENGTH)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: DueDate = None
    tag_ids: TagIds | None = None

    @model_validator(mode="after")
    def _reject_null_required(self):
        # description/due_date được phép null (xóa giá trị), còn các field NOT NULL thì không
        reject_null_fields(self, "title", "status", "priority", "tag_ids")
        return self


class TaskAssign(InputSchema):
    assignee_id: PositiveInt | None = Field(
        description="User id được giao; null = bỏ assign", examples=[2]
    )


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


class BookmarkOut(BaseModel):
    task_id: int
    bookmarked: bool


class ActivityOut(ORMSchema):
    id: int
    action: ActivityAction
    detail: str | None
    actor: UserPublic
    created_at: datetime
