from datetime import datetime

from pydantic import Field, model_validator

from app.schemas.common import InputSchema, ORMSchema
from app.schemas.task import TaskBrief
from app.schemas.user import UserPublic


# ---------- Input ----------
class ProjectCreate(InputSchema):
    name: str = Field(min_length=1, max_length=100, examples=["TaskHub Backend"])
    description: str | None = Field(default=None, examples=["Xây dựng RESTful API cho TaskHub"])


class ProjectUpdate(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None

    @model_validator(mode="after")
    def _reject_null_name(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


# ---------- Output ----------
class ProjectBrief(ORMSchema):
    id: int
    name: str


class ProjectOut(ORMSchema):
    id: int
    name: str
    description: str | None
    owner: UserPublic  # nested model: PM của project
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectOut):
    """Project kèm danh sách task (nested), mỗi task kèm assignee (nested 2 cấp)."""

    tasks: list[TaskBrief]
