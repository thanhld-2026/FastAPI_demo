from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field, PositiveInt, model_validator

from app.core import messages
from app.core.constants import REQUIRED_TEXT_MIN_LENGTH, WORKSPACE_NAME_MAX_LENGTH
from app.models.enums import WorkspaceRole
from app.schemas.common import InputSchema, ORMSchema, reject_null_fields
from app.schemas.user import UserPublic


def _not_owner(role: WorkspaceRole) -> WorkspaceRole:
    # Mỗi workspace có đúng 1 OWNER (người tạo, workspaces.owner_id): không mời / đổi sang OWNER
    if role == WorkspaceRole.OWNER:
        raise ValueError(messages.OWNER_ROLE_NOT_ASSIGNABLE)
    return role


AssignableRole = Annotated[WorkspaceRole, AfterValidator(_not_owner)]


# ---------- Input ----------
class WorkspaceCreate(InputSchema):
    name: str = Field(
        min_length=REQUIRED_TEXT_MIN_LENGTH,
        max_length=WORKSPACE_NAME_MAX_LENGTH,
        examples=["Backend Team"],
    )


class WorkspaceUpdate(InputSchema):
    name: str | None = Field(
        default=None, min_length=REQUIRED_TEXT_MIN_LENGTH, max_length=WORKSPACE_NAME_MAX_LENGTH
    )

    @model_validator(mode="after")
    def _reject_null_name(self):
        reject_null_fields(self, "name")
        return self


class MemberInvite(InputSchema):
    email: EmailStr = Field(examples=["carol@example.com"])
    role: AssignableRole = WorkspaceRole.EDITOR


class OwnershipTransfer(InputSchema):
    user_id: PositiveInt = Field(description="Thành viên đang hoạt động sẽ thành OWNER mới")


class MemberRoleUpdate(InputSchema):
    role: AssignableRole


# ---------- Output ----------
class WorkspaceOut(ORMSchema):
    id: int
    name: str
    owner: UserPublic
    created_at: datetime


class WorkspaceMemberOut(ORMSchema):
    user: UserPublic
    role: WorkspaceRole
    created_at: datetime


class WorkspaceDetail(WorkspaceOut):
    members: list[WorkspaceMemberOut]
