from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
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
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Tag already exists")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tag not found")
    crud.tag.delete(db, tag)
