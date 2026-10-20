"""Kết nối database: engine, session factory, Base class và dependency get_db."""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Quy tắc đặt tên constraint cố định -> Alembic sinh migration ổn định, dễ đọc
# (ví dụ: fk_tasks_project_id_projects thay vì tên ngẫu nhiên do DB tự sinh).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Class cha của mọi SQLAlchemy model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# pool_pre_ping: kiểm tra connection còn sống trước khi dùng (tránh lỗi khi DB restart)
engine = create_engine(settings.DATABASE_URL, echo=settings.DB_ECHO, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db() -> Generator[Session]:
    """Dependency: mỗi request dùng 1 session riêng, request xong thì đóng.

    - Nếu có exception -> rollback để không lưu dữ liệu dở dang.
    - FastAPI cache dependency trong 1 request, nên mọi nơi Depends(get_db)
      trong cùng request đều nhận CÙNG một session.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
