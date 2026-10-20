from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import IntegrityError

from app import crud
from app.cache import cache_delete, cache_get, cache_set
from app.config import settings
from app.core import messages
from app.core.exceptions import ConflictException
from app.core.responses import error_responses
from app.dependencies import DbSession, TagDep, verify_admin_role
from app.schemas.tag import TagCreate, TagOut

router = APIRouter(prefix="/api/tags", tags=["Tags"])

TAGS_CACHE_KEY = "taskhub:tags:all"


@router.get("", response_model=list[TagOut], summary="Danh sách tag (có cache Redis)")
def list_tags(db: DbSession, response: Response):
    """Cache-aside: đọc cache trước; miss thì đọc DB rồi ghi lại vào cache.

    Header `X-Cache: HIT | MISS` giúp quan sát cache hoạt động khi demo.
    """
    cached = cache_get(TAGS_CACHE_KEY)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    tags = [TagOut.model_validate(tag).model_dump() for tag in crud.tag.list_tags(db)]
    cache_set(TAGS_CACHE_KEY, tags, ttl=settings.TAGS_CACHE_TTL)
    response.headers["X-Cache"] = "MISS"
    return tags


@router.post(
    "",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_role)],
    summary="[Admin] Tạo tag",
    responses=error_responses(401, 403, 409),
)
def create_tag(data: TagCreate, db: DbSession):
    if crud.tag.get_by_name(db, data.name):
        raise ConflictException(messages.TAG_ALREADY_EXISTS)
    try:
        tag = crud.tag.create(db, data)
    except IntegrityError:
        # 2 request tạo cùng tên gần như đồng thời -> UNIQUE trong DB chặn request sau
        db.rollback()
        raise ConflictException(messages.TAG_ALREADY_EXISTS) from None
    cache_delete(TAGS_CACHE_KEY)  # dữ liệu đổi -> xóa cache để lần đọc sau lấy dữ liệu mới
    return tag


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_admin_role)],
    summary="[Admin] Xóa tag",
    responses=error_responses(401, 403, 404),
)
def delete_tag(tag: TagDep, db: DbSession):
    crud.tag.delete(db, tag)
    cache_delete(TAGS_CACHE_KEY)
