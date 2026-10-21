from datetime import datetime

from pydantic import Field

from app.core.constants import COMMENT_MAX_LENGTH
from app.schemas.common import InputSchema, ORMSchema
from app.schemas.user import UserPublic


class CommentCreate(InputSchema):
    content: str = Field(
        min_length=1, max_length=COMMENT_MAX_LENGTH, examples=["Mình đã review xong, LGTM!"]
    )


class CommentUpdate(CommentCreate):
    pass


class CommentOut(ORMSchema):
    id: int
    content: str
    task_id: int
    author: UserPublic
    created_at: datetime
    updated_at: datetime
