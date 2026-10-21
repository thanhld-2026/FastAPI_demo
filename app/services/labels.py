"""Label theo project + cache Redis cho danh sách label của từng project.

Cache-aside: đọc cache trước, miss thì đọc DB rồi ghi lại (có TTL); label thay đổi thì xóa
key của ĐÚNG project đó (project khác không bị ảnh hưởng). Redis lỗi -> đọc thẳng DB (app/cache.py).
"""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.cache import cache_delete, cache_get, cache_set
from app.config import settings
from app.core import messages
from app.core.exceptions import ConflictException
from app.models import Label, Project
from app.schemas.label import LabelCreate, LabelOut, LabelUpdate


def cache_key(project_id: int) -> str:
    return f"taskhub:projects:{project_id}:labels"


def list_labels(db: Session, project_id: int) -> tuple[list[dict[str, Any]], bool]:
    """Trả về (danh sách label, có lấy từ cache không)."""
    key = cache_key(project_id)
    cached = cache_get(key)
    if cached is not None:
        return cached, True
    labels = [
        LabelOut.model_validate(label).model_dump()
        for label in crud.label.list_for_project(db, project_id)
    ]
    cache_set(key, labels, ttl=settings.LABELS_CACHE_TTL)
    return labels, False


def create_label(db: Session, project: Project, data: LabelCreate) -> Label:
    try:
        label = crud.label.create(db, project, data)
    except IntegrityError:
        # UNIQUE (project_id, name): trùng tên trong project, kể cả 2 request đồng thời
        db.rollback()
        raise ConflictException(messages.LABEL_ALREADY_EXISTS) from None
    cache_delete(cache_key(project.id))
    return label


def update_label(db: Session, label: Label, data: LabelUpdate) -> Label:
    project_id = label.project_id
    try:
        updated = crud.label.update(db, label, data)
    except IntegrityError:
        db.rollback()
        raise ConflictException(messages.LABEL_ALREADY_EXISTS) from None
    cache_delete(cache_key(project_id))
    return updated


def delete_label(db: Session, label: Label) -> None:
    project_id = label.project_id
    crud.label.delete(db, label)
    cache_delete(cache_key(project_id))
