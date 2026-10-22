from fastapi import APIRouter, Response, status

from app.core.responses import error_responses
from app.dependencies import (
    CurrentUser,
    DbSession,
    EditableLabel,
    EditableProject,
    ReadableProject,
)
from app.schemas.label import LabelCreate, LabelOut, LabelUpdate
from app.services import labels as label_service

router = APIRouter(tags=["Labels"])


@router.get(
    "/projects/{project_id}/labels",
    response_model=list[LabelOut],
    summary="Label của project (có cache Redis, header X-Cache: HIT | MISS)",
    responses=error_responses(401, 403, 404),
)
def list_labels(project: ReadableProject, db: DbSession, response: Response):
    # Không phân trang: mỗi project chỉ có vài chục label, FE dùng để đổ dropdown
    labels, from_cache = label_service.list_labels(db, project.id)
    response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
    return labels


@router.post(
    "/projects/{project_id}/labels",
    response_model=LabelOut,
    status_code=status.HTTP_201_CREATED,
    summary="[EDITOR] Tạo label trong project",
    responses=error_responses(401, 403, 404, 409),
)
def create_label(data: LabelCreate, project: EditableProject, db: DbSession):
    return label_service.create_label(db, project, data)


@router.patch(
    "/labels/{label_id}",
    response_model=LabelOut,
    summary="[EDITOR] Đổi tên / màu label",
    responses=error_responses(401, 403, 404, 409),
)
def update_label(data: LabelUpdate, label: EditableLabel, db: DbSession):
    return label_service.update_label(db, label, data)


@router.delete(
    "/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[EDITOR] Xóa label (tự gỡ khỏi các task, có ghi activity cho từng task)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_label(label: EditableLabel, current_user: CurrentUser, db: DbSession):
    label_service.delete_label(db, label, actor=current_user)
