from fastapi import APIRouter, Depends, status

from app import crud
from app.core import messages
from app.core.exceptions import ConflictException
from app.dependencies import DbSession, TagDep, verify_admin_role
from app.schemas.tag import TagCreate, TagOut

router = APIRouter(prefix="/api/tags", tags=["Tags"])


@router.get("", response_model=list[TagOut], summary="Danh sách tag")
def list_tags(db: DbSession):
    return crud.tag.list_tags(db)


@router.post(
    "",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_role)],
    summary="[Admin] Tạo tag",
)
def create_tag(data: TagCreate, db: DbSession):
    if crud.tag.get_by_name(db, data.name):
        raise ConflictException(messages.TAG_ALREADY_EXISTS)
    return crud.tag.create(db, data)


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_admin_role)],
    summary="[Admin] Xóa tag",
)
def delete_tag(tag: TagDep, db: DbSession):
    crud.tag.delete(db, tag)
