"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env.

pydantic-settings dùng python-dotenv để đọc file .env, sau đó validate kiểu dữ liệu
(ví dụ DB_ECHO phải là bool). Thứ tự ưu tiên:
biến môi trường thật > file .env > giá trị mặc định trong class.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "TaskHub API"
    ENVIRONMENT: str = "development"

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://taskhub:taskhub@localhost:5432/taskhub"
    DB_ECHO: bool = False  # True -> in toàn bộ câu SQL ra log (hữu ích khi soi N+1 query)


settings = Settings()
