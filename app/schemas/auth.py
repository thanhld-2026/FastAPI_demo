from pydantic import BaseModel, Field

from app.core.constants import REFRESH_TOKEN_MAX_LENGTH
from app.schemas.common import InputSchema


class TokenPair(BaseModel):
    """Response của login / refresh. Field `access_token` + `token_type` theo chuẩn OAuth2
    (Swagger UI đọc 2 field này cho nút Authorize)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Số giây access token còn hiệu lực")


class RefreshTokenIn(InputSchema):
    refresh_token: str = Field(min_length=1, max_length=REFRESH_TOKEN_MAX_LENGTH)
