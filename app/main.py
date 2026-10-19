"""Entry point: tạo FastAPI app và gắn các router.

Chạy local:  uvicorn app.main:app --reload
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.routers import projects, tasks, users

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="RESTful API quản lý dự án & công việc (khóa học FastAPI).",
)


# ---------- Routers ----------
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(tasks.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health"], summary="Kiểm tra app + kết nối database")
def health(db: Annotated[Session, Depends(get_db)]):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
