from app.schemas.common import ORMSchema


# ---------- Output ----------
class UserPublic(ORMSchema):
    """Thông tin công khai, dùng khi lồng (nested) trong project/task/comment."""

    id: int
    username: str
    full_name: str | None
