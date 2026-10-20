"""Entry point: tạo FastAPI app, gắn middleware, exception handler và các router.

Chạy local:  uvicorn app.main:app --reload
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app.config import settings
from app.core import messages
from app.core.exceptions import AppException, app_exception_handler
from app.dependencies import DbSession
from app.logging_config import setup_logging
from app.routers import comments, projects, tags, tasks, users

setup_logging(settings.LOG_LEVEL, settings.LOG_FILE)
logger = logging.getLogger("taskhub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code trước `yield` chạy 1 lần khi server khởi động, sau `yield` chạy khi tắt
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="RESTful API quản lý dự án & công việc (khóa học FastAPI).",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},  # giữ token khi reload /docs
)


# ---------- Middleware ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Ghi log mỗi request: method, path, status code, thời gian xử lý, request id.

    Request id được trả về trong header X-Request-ID -> khi user báo lỗi,
    chỉ cần id này là tìm được đúng dòng log trên server.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "[%s] %s %s -> 500 (%.1f ms)",
            request_id, request.method, request.url.path, duration_ms,
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "[%s] %s %s -> %s (%.1f ms)",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# CORS được add SAU CÙNG nên nằm ngoài cùng -> mọi response (kể cả lỗi) đều có header CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # chỉ cho phép các domain frontend đã khai báo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Cache"],  # cho phép JS ở frontend đọc 2 header này
)


# ---------- Exception handler ----------
# Lỗi nghiệp vụ (NotFound, Forbidden, Conflict...) -> {"detail": ...} với status code tương ứng
app.add_exception_handler(AppException, app_exception_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Lỗi không lường trước: ghi đầy đủ traceback vào log, client chỉ nhận thông báo chung
    (không lộ chi tiết nội bộ như câu SQL, đường dẫn file...)."""
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("[%s] Unhandled error on %s %s", request_id, request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": messages.INTERNAL_SERVER_ERROR, "request_id": request_id},
    )


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
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check failed: database unreachable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unreachable"},
        )
    return {"status": "ok", "database": "ok"}
