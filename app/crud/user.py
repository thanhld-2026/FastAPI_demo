from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Task, User, UserRole
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
    if "password" in values:
        user.hashed_password = hash_password(values.pop("password"))
    if "email" in values:
        values["email"] = values["email"].lower()
    for field, value in values.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


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


def list_users(db: Session, *, skip: int, limit: int) -> tuple[list[User], int]:
    total = db.scalar(select(func.count()).select_from(User))
    users = db.scalars(select(User).order_by(User.id).offset(skip).limit(limit)).all()
    return list(users), total


def get_profile(db: Session, username: str) -> User | None:
    """User kèm project đang quản lý + task được giao, load sẵn trong 3 query cố định."""
    stmt = (
        select(User)
        .where(User.username == username)
        .options(
            selectinload(User.owned_projects),
            selectinload(User.assigned_tasks).joinedload(Task.assignee),
        )
    )
    return db.scalar(stmt)
