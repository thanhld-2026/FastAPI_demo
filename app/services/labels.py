"""Label theo project + cache Redis cho danh sách label của từng project.

Cache-aside có version: mỗi project có 1 key version (`...:labels:version`), dữ liệu nằm ở key
`...:labels:v<version>` (có TTL). Label thay đổi -> tăng version SAU khi commit, key cũ bị bỏ
(xem app/cache.py: tránh ghi dữ liệu cũ lại vào cache). Project khác không bị ảnh hưởng.
Redis lỗi -> đọc thẳng DB.
"""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.cache import cache_bump_version, cache_get, cache_set, cache_version
from app.config import settings
from app.core import messages
from app.core.exceptions import ConflictException
from app.models import ActivityAction, Label, Project, User
from app.schemas.label import LabelCreate, LabelOut, LabelUpdate


def _version_key(project_id: int) -> str:
    return f"taskhub:projects:{project_id}:labels:version"


def cache_key(project_id: int, version: int) -> str:
    return f"taskhub:projects:{project_id}:labels:v{version}"


def invalidate_cache(project_id: int, *, project_deleted: bool = False) -> None:
    """Gọi SAU commit. Key version không có TTL (mỗi project 1 số nhỏ); project bị xóa thì cho
    hết hạn sau khi chắc chắn mọi key dữ liệu của nó đã hết hạn."""
    ttl = settings.LABELS_CACHE_TTL if project_deleted else None
    cache_bump_version(_version_key(project_id), ttl=ttl)


def list_labels(db: Session, project_id: int) -> tuple[list[dict[str, Any]], bool]:
    """Trả về (danh sách label, có lấy từ cache không)."""
    version = cache_version(_version_key(project_id))
    if version is not None:
        cached = cache_get(cache_key(project_id, version))
        if cached is not None:
            return cached, True
    labels = [
        LabelOut.model_validate(label).model_dump()
        for label in crud.label.list_for_project(db, project_id)
    ]
    if version is not None:
        cache_set(cache_key(project_id, version), labels, ttl=settings.LABELS_CACHE_TTL)
    return labels, False


def create_label(db: Session, project: Project, data: LabelCreate) -> Label:
    try:
        label = crud.label.create(db, project, data)
    except IntegrityError:
        # UNIQUE (project_id, name): trùng tên trong project, kể cả 2 request đồng thời
        db.rollback()
        raise ConflictException(messages.LABEL_ALREADY_EXISTS) from None
    invalidate_cache(project.id)
    return label


def update_label(db: Session, label: Label, data: LabelUpdate) -> Label:
    project_id = label.project_id
    try:
        updated = crud.label.update(db, label, data)
    except IntegrityError:
        db.rollback()
        raise ConflictException(messages.LABEL_ALREADY_EXISTS) from None
    invalidate_cache(project_id)
    return updated


def delete_label(db: Session, label: Label, actor: User) -> None:
    """Xóa label: DB tự gỡ label khỏi các task (ON DELETE CASCADE). Mỗi task bị gỡ được ghi
    activity + cập nhật updated_at như khi gỡ bằng tay, trong cùng 1 commit.

    Dòng label đã bị khóa (EditableLabel) nên không request nào gắn thêm label này được nữa.
    """
    project_id, name = label.project_id, label.name
    tasks = crud.task.lock_tasks_with_label(db, label.id)
    crud.task.touch(db, [task.id for task in tasks])
    for task in tasks:
        crud.activity.add(
            db,
            task=task,
            actor=actor,
            action=ActivityAction.UPDATED,
            detail=f"removed label {name} (label deleted)",
        )
    crud.label.delete(db, label)
    invalidate_cache(project_id)
