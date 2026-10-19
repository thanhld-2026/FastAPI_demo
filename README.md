# TaskHub API

RESTful API quản lý **project** và **task** (giống Jira/Trello thu nhỏ), xây dựng bằng FastAPI.

| Thành phần | Công nghệ |
|---|---|
| Web framework | FastAPI + Uvicorn |
| ORM / Migration | SQLAlchemy 2 + Alembic |
| Database | PostgreSQL 17 (driver psycopg 3) |
| Cấu hình | pydantic-settings, python-dotenv |
| Xác thực | OAuth2 Password Flow + JWT (PyJWT), băm mật khẩu bằng bcrypt |
| Test | pytest + TestClient + SQLite in-memory |

## Chạy ở máy local

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # rồi đổi SECRET_KEY

docker compose up -d db          # bật PostgreSQL
alembic upgrade head             # tạo bảng
python -m scripts.seed           # dữ liệu mẫu
uvicorn app.main:app --reload    # http://localhost:8000/docs
```

Tài khoản mẫu: `admin`, `alice`, `bob`, `carol`, `dave`, dùng chung mật khẩu **`Password123`**.
Trên Swagger bấm nút **Authorize** để đăng nhập.

## Chạy test

```bash
pytest          # KHÔNG cần PostgreSQL: test dùng SQLite in-memory
```

## Cấu trúc thư mục

```
app/
├── main.py         # Tạo app, gắn router
├── config.py       # Đọc cấu hình từ .env (pydantic-settings)
├── database.py     # engine, SessionLocal, Base, dependency get_db
├── security.py     # bcrypt hash/verify, tạo/giải mã JWT
├── dependencies.py # get_db, get_current_user, ...
├── models/         # SQLAlchemy model = bảng trong DB
├── schemas/        # Pydantic schema = hình dạng dữ liệu vào/ra API
├── crud/           # Truy cập DB
└── routers/        # Endpoint HTTP (APIRouter)
alembic/            # Migration database
scripts/seed.py     # Dữ liệu mẫu
tests/              # pytest
```
