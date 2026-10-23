from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.crud.workspace import visible_to
from app.models import Project, Task, User, UserRole
from app.schemas.common import PageParams
from app.schemas.user import AdminUserUpdate, UserCreate, UserUpdate
from app.security import DUMMY_HASH, hash_password, verify_password


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def create(db: Session, data: UserCreate, *, role: UserRole = UserRole.MEMBER) -> User:
    user = User(
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


def get_for_update(db: Session, user_id: int) -> User | None:
    """SELECT ... FOR UPDATE + đọc lại dòng user: refresh token, đổi mật khẩu, khóa tài khoản của
    cùng 1 user chạy tuần tự (xem services/auth.py)."""
    stmt = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Đăng nhập bằng email. Trả về None nếu sai thông tin."""
    user = get_by_email(db, email)
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


def get_profile(db: Session, user_id: int, *, viewer: User) -> User | None:
    """User kèm project user đã tạo + task user được giao, load sẵn (3 query cố định).

    Chỉ giữ project / task trong workspace mà `viewer` cũng là thành viên (admin: tất cả): profile
    không được làm lộ dữ liệu của workspace người xem không có quyền. Điều kiện lọc gắn thẳng vào
    relationship bằng `.and_(...)` (loader criteria), nên trả về object User và để schema
    UserProfile tự đọc field (thêm field vào schema không phải sửa ở đây).

    Lưu ý: 2 collection của object này chỉ chứa phần đã lọc, chỉ dùng để trả response.
    populate_existing: lỡ object User đã có trong session (xem profile của chính mình) thì vẫn
    nạp lại collection theo điều kiện lọc.
    """
    visible_projects = select(Project.id).where(visible_to(viewer, Project.workspace_id))
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.created_projects.and_(visible_to(viewer, Project.workspace_id))),
            selectinload(User.assigned_tasks.and_(Task.project_id.in_(visible_projects))).joinedload(
                Task.assignee
            ),
        )
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)
