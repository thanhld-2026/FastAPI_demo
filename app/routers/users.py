from fastapi import APIRouter, HTTPException, status

from app import crud
from app.dependencies import DbSession
from app.schemas.profile import UserProfile

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/{username}/profile", response_model=UserProfile, summary="Trang cá nhân công khai")
def get_profile(username: str, db: DbSession):
    user = crud.user.get_profile(db, username)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
