from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Label, Project
from app.schemas.label import LabelCreate, LabelUpdate


def get(db: Session, label_id: int) -> Label | None:
    return db.get(Label, label_id)


def get_for_update(db: Session, label_id: int) -> Label | None:
    """SELECT ... FOR UPDATE + đọc lại: sửa / xóa label. Request đang gắn label này (giữ FOR
    SHARE, xem get_in_project) phải xong trước, và không gắn thêm được trong lúc đang xóa."""
    stmt = (
        select(Label)
        .where(Label.id == label_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)


def list_for_project(db: Session, project_id: int) -> list[Label]:
    stmt = select(Label).where(Label.project_id == project_id).order_by(Label.name)
    return list(db.scalars(stmt).all())


def get_in_project(
    db: Session, project_id: int, label_id: int, *, for_share: bool = False
) -> Label | None:
    """Label thuộc đúng project (label của project khác coi như không tồn tại)."""
    labels = get_many_in_project(db, project_id, [label_id], for_share=for_share)
    return labels[0] if labels else None


def get_many_in_project(
    db: Session, project_id: int, label_ids: list[int], *, for_share: bool = False
) -> list[Label]:
    """Chỉ lấy label thuộc đúng project: không gắn được label của project khác vào task.

    for_share: SELECT ... FOR SHARE tới hết transaction, label không bị xóa trong lúc đang được
    gắn vào task (nếu không, INSERT task_labels vi phạm khóa ngoại -> 500).
    """
    if not label_ids:
        return []
    stmt = select(Label).where(Label.project_id == project_id, Label.id.in_(label_ids))
    if for_share:
        stmt = stmt.with_for_update(read=True)
    return list(db.scalars(stmt.order_by(Label.id)).all())


def create(db: Session, project: Project, data: LabelCreate) -> Label:
    label = Label(project=project, name=data.name, color=data.color)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


def update(db: Session, label: Label, data: LabelUpdate) -> Label:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(label, field, value)
    db.commit()
    db.refresh(label)
    return label


def delete(db: Session, label: Label) -> None:
    # passive_deletes: ORM không tự load task / xóa từng dòng task_labels, để DB CASCADE làm
    db.delete(label)
    db.commit()
