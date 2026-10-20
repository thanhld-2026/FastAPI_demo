from fastapi import APIRouter, Depends, status

from app import crud
from app.core import messages
from app.core.exceptions import ConflictException, NotFoundException
from app.dependencies import DbSession, verify_admin_role
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
def delete_tag(tag_id: int, db: DbSession):
    tag = crud.tag.get(db, tag_id)
    if tag is None:
        raise NotFoundException(messages.TAG_NOT_FOUND)
    crud.tag.delete(db, tag)
