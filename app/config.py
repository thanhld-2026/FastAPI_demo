"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env.

pydantic-settings dùng python-dotenv để đọc file .env, sau đó validate kiểu dữ liệu
(ví dụ ACCESS_TOKEN_EXPIRE_MINUTES phải là int). Thứ tự ưu tiên:
biến môi trường thật > file .env > giá trị mặc định trong class.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "TaskHub API"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str | None = "logs/app.log"

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://taskhub:taskhub@localhost:5432/taskhub"
    DB_ECHO: bool = False  # True -> in toàn bộ câu SQL ra log (hữu ích khi soi N+1 query)

    # --- JWT / Security ---
    # Bắt buộc phải khai báo, không có giá trị mặc định -> tránh vô tình dùng key yếu
    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Redis cache ---
    REDIS_URL: str | None = None  # None / rỗng -> tắt cache
    TAGS_CACHE_TTL: int = 300  # giây

    # --- Email ---
    EMAIL_ENABLED: bool = False  # False -> chỉ ghi log thay vì gửi mail thật
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = False
    EMAIL_FROM: str = "TaskHub <no-reply@taskhub.local>"


settings = Settings()
