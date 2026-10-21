from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.crud.workspace import member_workspace_ids
from app.models import Project, Task, User, UserRole
from app.schemas.common import PageParams
from app.schemas.user import AdminUserUpdate, UserCreate, UserUpdate
from app.security import DUMMY_HASH, hash_password, verify_password


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def create(db: Session, data: UserCreate, *, role: UserRole = UserRole.MEMBER) -> User:
    user = User(
        username=data.username,
        email=data.email.lower(),
        full_name=data.full_name,
        hashed_password=hash_password(data.password),  # không bao giờ lưu mật khẩu gốc
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update(db: Session, user: User, data: UserUpdate) -> User:
    values = data.model_dump(exclude_unset=True)
    if "email" in values:
        values["email"] = values["email"].lower()
    for field, value in values.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def set_password(user: User, password: str) -> None:
    """Đổi hash mật khẩu, KHÔNG commit (service commit cùng việc thu hồi các phiên đăng nhập)."""
    user.hashed_password = hash_password(password)


def admin_update(db: Session, user: User, data: AdminUserUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, identifier: str, password: str) -> User | None:
    """Đăng nhập bằng username HOẶC email. Trả về None nếu sai thông tin."""
    user = db.scalar(
        select(User).where(or_(User.username == identifier, User.email == identifier.lower()))
    )
    if user is None:
        verify_password(password, DUMMY_HASH)  # giữ thời gian phản hồi đồng đều
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def list_users(db: Session, pagination: PageParams) -> tuple[list[User], int]:
    total = db.execute(select(func.count()).select_from(User)).scalar_one()
    stmt = select(User).order_by(User.id).offset(pagination.offset).limit(pagination.limit)
    users = db.scalars(stmt).all()
    return list(users), total


def get_profile(
    db: Session, username: str, *, viewer: User, include_all: bool = False
) -> dict[str, Any] | None:
    """Thông tin công khai + project user đã tạo + task user được giao, 3 query cố định.

    Chỉ liệt kê project / task trong workspace mà `viewer` cũng là thành viên: profile không được
    làm lộ dữ liệu của workspace người xem không có quyền (`include_all` cho admin).
    """
    user = get_by_username(db, username)
    if user is None:
        return None
    projects = select(Project).where(Project.creator_id == user.id).order_by(Project.id)
    tasks = (
        select(Task)
        .where(Task.assignee_id == user.id)
        .options(joinedload(Task.assignee))
        .order_by(Task.id)
    )
    if not include_all:
        visible = member_workspace_ids(viewer.id)
        projects = projects.where(Project.workspace_id.in_(visible))
        tasks = tasks.join(Project, Project.id == Task.project_id).where(
            Project.workspace_id.in_(visible)
        )
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "bio": user.bio,
        "created_at": user.created_at,
        "created_projects": list(db.scalars(projects).all()),
        "assigned_tasks": list(db.scalars(tasks).all()),
    }
