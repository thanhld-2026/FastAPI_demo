from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.crud.workspace import visible_to
from app.models import Project, ProjectStatus, Task, User, Workspace
from app.schemas.common import PageParams
from app.schemas.project import ProjectCreate, ProjectUpdate


def get(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def lock_status(db: Session, project_id: int) -> ProjectStatus | None:
    """Đọc status của project, khóa chia sẻ dòng project (SELECT ... FOR SHARE) tới hết
    transaction: các request ghi task / comment cùng giữ được, nhưng archive (UPDATE dòng project)
    phải chờ chúng commit; request đến sau archive thì chờ archive commit rồi đọc được status mới
    -> không ghi lọt vào project đã archive. Request sửa / xóa chính dòng project dùng
    get_for_update. Trả về None nếu project không còn. (SQLite bỏ qua mệnh đề khóa.)
    """
    stmt = select(Project.status).where(Project.id == project_id).with_for_update(read=True)
    return db.scalar(stmt)


def get_for_update(db: Session, project_id: int) -> Project | None:
    """SELECT ... FOR UPDATE + đọc lại (populate_existing): request sắp ghi lên chính dòng project
    phải làm việc trên dữ liệu mới nhất, không phải bản đã load trước khi có khóa. Nếu không,
    request đến sau có thể so với bản cũ, thấy "không đổi gì" và bỏ qua UPDATE (mất cập nhật)."""
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)


def get_detail(db: Session, project_id: int) -> Project | None:
    """Project + creator + tasks + assignee của từng task.

    - joinedload(creator): quan hệ Many-to-One -> JOIN luôn trong câu query chính.
    - selectinload(tasks): quan hệ One-to-Many -> 1 query phụ `WHERE project_id IN (...)`,
      tránh JOIN làm nhân bản dòng của project.
    - .joinedload(Task.assignee): load lồng tiếp assignee của mỗi task (chained loading).
    => Tổng cộng 2 query dù project có 1 hay 1000 task.
    """
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            joinedload(Project.creator),
            selectinload(Project.tasks).joinedload(Task.assignee),
        )
    )
    return db.scalar(stmt)


def list_projects(
    db: Session,
    pagination: PageParams,
    *,
    viewer: User,
    status: ProjectStatus | None = None,
    workspace_id: int | None = None,
) -> tuple[list[Project], int]:
    """Project trong các workspace `viewer` là thành viên (admin: tất cả)."""
    conditions = [visible_to(viewer, Project.workspace_id)]
    if status is not None:
        conditions.append(Project.status == status)
    if workspace_id is not None:
        conditions.append(Project.workspace_id == workspace_id)
    total = db.execute(select(func.count()).select_from(Project).where(*conditions)).scalar_one()
    stmt = (
        select(Project)
        .where(*conditions)
        .options(joinedload(Project.creator))  # tránh N+1 khi trả về creator của từng project
        .order_by(Project.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all()), total


def create(db: Session, data: ProjectCreate, *, workspace: Workspace, creator: User) -> Project:
    project = Project(**data.model_dump(), workspace=workspace, creator=creator)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update(db: Session, project: Project, data: ProjectUpdate) -> Project:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


def delete(db: Session, project: Project) -> None:
    db.delete(project)  # cascade xóa luôn tasks -> comments, activities
    db.commit()


def set_status(db: Session, project: Project, status: ProjectStatus) -> Project:
    project.status = status
    db.commit()
    db.refresh(project)
    return project
