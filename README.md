# TaskHub API

RESTful API quản lý **project** và **task** (giống Jira/Trello thu nhỏ), xây dựng bằng FastAPI.

| Thành phần | Công nghệ |
|---|---|
| Web framework | FastAPI + Uvicorn |
| ORM / Migration | SQLAlchemy 2 + Alembic |
| Database | PostgreSQL 17 (driver psycopg 3) |
| Cấu hình | pydantic-settings, python-dotenv |
| Xác thực | OAuth2 Password Flow + JWT (PyJWT), băm mật khẩu bằng bcrypt |
| Cache | Redis |
| Email (dev) | Mailpit (SMTP giả lập, có giao diện web) |
| Test | pytest + TestClient + SQLite in-memory + fakeredis |

## Chạy ở máy local

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # rồi đổi SECRET_KEY

docker compose up -d db redis mailpit   # PostgreSQL + Redis + Mailpit
alembic upgrade head             # tạo bảng
python -m scripts.seed           # dữ liệu mẫu
uvicorn app.main:app --reload    # http://localhost:8000/docs
```

Tài khoản mẫu: `admin`, `alice`, `bob`, `carol`, `dave`, dùng chung mật khẩu **`Password123`**.
Trên Swagger bấm nút **Authorize** để đăng nhập.
Email thông báo comment (gửi ngầm bằng BackgroundTasks) xem tại Mailpit: <http://localhost:8025>.

## Quy ước API

- Các API **đọc** (GET) công khai, các API **ghi** đều cần đăng nhập. PM là người tạo project.
  Khi làm RBAC theo workspace (phụ lục đặc tả), quyền đọc sẽ theo membership và cần đăng nhập.
- Lỗi luôn trả về dạng `{"detail": "..."}`; các mã lỗi của từng endpoint có trên Swagger:
  `400` body tham chiếu dữ liệu không tồn tại, `401` chưa đăng nhập / token sai,
  `403` không đủ quyền, `404` không tìm thấy, `409` trùng dữ liệu, `422` sai định dạng.
- Danh sách phân trang bằng `skip` / `limit` (mặc định 20, tối đa 100), response có `total`.

## Chạy test

```bash
pytest          # KHÔNG cần PostgreSQL / Redis: SQLite in-memory + fakeredis
pytest -v tests/test_tasks.py::test_register_login_and_create_task_flow   # integration test Đăng ký -> Tạo Task
```

## Cấu trúc thư mục

```
app/
├── main.py         # Tạo app, gắn router
├── config.py       # Đọc cấu hình từ .env (pydantic-settings)
├── database.py     # engine, SessionLocal, Base, dependency get_db
├── security.py     # bcrypt hash/verify, tạo/giải mã JWT
├── dependencies.py # get_current_user, phân quyền, load resource, phân trang
├── permissions.py  # Quy tắc phân quyền nghiệp vụ
├── core/           # Exception + handler, message lỗi, hằng số, error responses
├── cache.py        # Redis cache (tự bỏ qua nếu Redis lỗi)
├── services/       # Gửi email (chạy ở background)
├── models/         # SQLAlchemy model = bảng trong DB
├── schemas/        # Pydantic schema = hình dạng dữ liệu vào/ra API
├── crud/           # Truy cập DB
└── routers/        # Endpoint HTTP (APIRouter)
alembic/            # Migration database
scripts/seed.py     # Dữ liệu mẫu
tests/              # pytest
```
