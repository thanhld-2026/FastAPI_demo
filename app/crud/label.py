from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Label, Project
from app.schemas.label import LabelCreate, LabelUpdate


def get(db: Session, label_id: int) -> Label | None:
    return db.get(Label, label_id)


def list_for_project(db: Session, project_id: int) -> list[Label]:
    stmt = select(Label).where(Label.project_id == project_id).order_by(Label.name)
    return list(db.scalars(stmt).all())


def get_many_in_project(db: Session, project_id: int, label_ids: list[int]) -> list[Label]:
    """Chỉ lấy label thuộc đúng project: không gắn được label của project khác vào task."""
    if not label_ids:
        return []
    stmt = select(Label).where(Label.project_id == project_id, Label.id.in_(label_ids))
    return list(db.scalars(stmt).all())


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
    db.delete(label)  # task_labels có ondelete CASCADE -> task tự mất label này
    db.commit()
