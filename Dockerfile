FROM python:3.13-slim

# PYTHONDONTWRITEBYTECODE: không sinh file .pyc trong container
# PYTHONUNBUFFERED: log in ra ngay lập tức (không bị buffer) -> `docker compose logs` thấy liền
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy requirements và cài TRƯỚC khi copy source code: tận dụng layer cache của Docker,
# sửa code không phải cài lại thư viện (chỉ build lại khi requirements.txt thay đổi).
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Chạy bằng user thường thay vì root -> giảm rủi ro bảo mật
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 1. Chạy migration để DB luôn đúng schema mới nhất
# 2. `exec` để uvicorn là process chính (PID 1) -> nhận được tín hiệu tắt (SIGTERM) từ Docker
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
