"""Exception nghiệp vụ dùng chung + handler global (đăng ký trong main.py).

Router / dependency chỉ cần `raise NotFoundException(messages.TASK_NOT_FOUND)`,
handler sẽ trả JSON `{"detail": "..."}` (giữ cùng format với HTTPException của FastAPI)
với status code tương ứng của từng loại lỗi.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers


class BadRequestException(AppException):
    """Body tham chiếu tới dữ liệu không tồn tại (khác 404 dành cho resource trên URL)."""

    status_code = status.HTTP_400_BAD_REQUEST


class UnauthorizedException(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, message: str) -> None:
        # Chuẩn OAuth2 Bearer: response 401 phải kèm header WWW-Authenticate
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenException(AppException):
    status_code = status.HTTP_403_FORBIDDEN


class NotFoundException(AppException):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictException(AppException):
    status_code = status.HTTP_409_CONFLICT


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}, headers=exc.headers
    )
