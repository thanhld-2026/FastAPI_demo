from fastapi import APIRouter

from app import crud
from app.dependencies import DbSession
from app.schemas.tag import TagOut

router = APIRouter(prefix="/api/tags", tags=["Tags"])


@router.get("", response_model=list[TagOut], summary="Danh sách tag")
def list_tags(db: DbSession):
    return crud.tag.list_tags(db)
