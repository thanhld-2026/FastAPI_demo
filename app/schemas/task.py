from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, PositiveInt, model_validator

from app.core import messages
from app.core.constants import TASK_TITLE_MAX_LENGTH
from app.models.enums import ActivityAction, TaskPriority, TaskStatus
from app.schemas.common import InputSchema, ORMSchema, reject_null_fields
from app.schemas.label import LabelOut
from app.schemas.user import UserPublic

# [1, 2, 2] -> [1, 2]: bỏ id trùng nhưng giữ nguyên thứ tự
LabelIds = Annotated[list[int], AfterValidator(lambda ids: list(dict.fromkeys(ids)))]


def _not_in_past(value: date | None) -> date | None:
    # Chỉ validate khi client có gửi due_date -> task đã quá hạn vẫn sửa được các field khác
    if value is not None and value < date.today():
        raise ValueError(messages.DUE_DATE_IN_PAST)
    return value


DueDate = Annotated[date | None, AfterValidator(_not_in_past)]


def _single_line(value: str) -> str:
    # Title được đưa vào tiêu đề email (header): ký tự xuống dòng làm header không hợp lệ
    if "\n" in value or "\r" in value:
        raise ValueError(messages.TITLE_MUST_BE_SINGLE_LINE)
    return value


TaskTitle = Annotated[
    str,
    Field(min_length=1, max_length=TASK_TITLE_MAX_LENGTH),
    AfterValidator(_single_line),
]


# ---------- Input ----------
class TaskCreate(InputSchema):
    title: TaskTitle = Field(examples=["Thiết kế database"])
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: DueDate = None
    label_ids: LabelIds = Field(default_factory=list, examples=[[1, 2]])


class TaskUpdate(InputSchema):
    """Partial update: chỉ field nào gửi lên mới được cập nhật."""

    title: TaskTitle | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: DueDate = None
    label_ids: LabelIds | None = None

    @model_validator(mode="after")
    def _reject_null_required(self):
        # description/due_date được phép null (xóa giá trị), còn các field NOT NULL thì không
        reject_null_fields(self, "title", "status", "priority", "label_ids")
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
    labels: list[LabelOut]
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
