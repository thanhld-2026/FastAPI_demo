"""Cấu hình chạy migration của Alembic.

Các lệnh thường dùng:
    alembic revision --autogenerate -m "mô tả thay đổi"   # so sánh model với DB -> sinh file migration
    alembic upgrade head                                  # áp dụng mọi migration chưa chạy
    alembic downgrade -1                                  # quay lui 1 migration
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

import app.models  # noqa: F401  (import để mọi model được đăng ký vào Base.metadata)
from app.config import settings
from app.database import Base

config = context.config

# Lấy URL database từ .env thay vì hardcode trong alembic.ini.
# ConfigParser coi "%" là ký tự đặc biệt nên phải escape thành "%%".
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic so sánh metadata này (các model) với schema thật trong DB để autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Sinh ra SQL thuần (alembic upgrade head --sql) mà không cần kết nối DB."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Kết nối DB và chạy migration trực tiếp."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # phát hiện cả thay đổi kiểu cột (vd: String(50) -> String(100))
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
