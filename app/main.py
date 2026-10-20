"""Entry point: tạo FastAPI app và gắn các router.

Chạy local:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.config import settings
from app.core.exceptions import AppException, app_exception_handler
from app.dependencies import DbSession
from app.routers import comments, projects, tags, tasks, users

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="RESTful API quản lý dự án & công việc (khóa học FastAPI).",
)

# Mọi AppException (NotFound, Forbidden, Conflict...) đều đi qua 1 handler chung
app.add_exception_handler(AppException, app_exception_handler)


# ---------- Routers ----------
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(tags.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health"], summary="Kiểm tra app + kết nối database")
def health(db: DbSession):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
