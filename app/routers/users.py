from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from app import crud
from app.dependencies import CurrentUser, DbSession
from app.schemas.profile import UserProfile
from app.schemas.user import Token, UserCreate, UserOut, UserUpdate
from app.security import create_access_token

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản",
)
def register(data: UserCreate, db: DbSession):
    if crud.user.get_by_username(db, data.username):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username already registered")
    if crud.user.get_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        return crud.user.create(db, data)
    except IntegrityError:
        # 2 request đăng ký cùng username gần như đồng thời: cả 2 đều qua bước kiểm tra
        # ở trên, nhưng UNIQUE constraint trong DB vẫn chặn được request thứ 2.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username or email already registered")


@router.post("/login", response_model=Token, summary="Đăng nhập (trả về access_token)")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    """Chuẩn OAuth2 Password Flow: gửi **form data** `username` + `password`
    (field `username` chấp nhận cả username hoặc email)."""
    user = crud.user.authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut, summary="Thông tin user đang đăng nhập")
def read_me(current_user: CurrentUser):
    return current_user


@router.put("/me", response_model=UserOut, summary="Cập nhật thông tin cá nhân")
def update_me(data: UserUpdate, current_user: CurrentUser, db: DbSession):
    email_changed = data.email and data.email.lower() != current_user.email
    if email_changed and crud.user.get_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")
    return crud.user.update(db, current_user, data)


@router.get("/{username}/profile", response_model=UserProfile, summary="Trang cá nhân công khai")
def get_profile(username: str, db: DbSession):
    user = crud.user.get_profile(db, username)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
