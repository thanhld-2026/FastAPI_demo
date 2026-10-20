"""Document các response lỗi trên OpenAPI (Swagger) qua tham số `responses=` của route.

FastAPI chỉ tự document 422 (sai định dạng input); các lỗi nghiệp vụ còn lại
phải khai báo để FE biết endpoint có thể trả về những case nào.
"""

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Format lỗi chung của API (xem app/core/exceptions.py)."""

    detail: str


_DESCRIPTIONS = {
    400: "Body tham chiếu tới dữ liệu không tồn tại hoặc thao tác không hợp lệ",
    401: "Chưa đăng nhập hoặc token không hợp lệ / hết hạn",
    403: "Không đủ quyền (hoặc tài khoản đã bị khóa)",
    404: "Không tìm thấy resource trên URL",
    409: "Trùng dữ liệu",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Ví dụ: `@router.put(..., responses=error_responses(401, 403, 404))`."""
    return {
        code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in status_codes
    }
