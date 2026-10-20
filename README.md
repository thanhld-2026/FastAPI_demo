# TaskHub API

RESTful API quản lý **project** và **task** (giống Jira/Trello thu nhỏ), xây dựng bằng FastAPI. Đây là bài thực hành của khóa FastAPI, đi lần lượt qua 8 mục: setup, CRUD, quan hệ model, xác thực JWT, phân quyền, nghiệp vụ & transaction, testing / background task / cache, triển khai.

| Thành phần | Công nghệ |
|---|---|
| Web framework | FastAPI 0.146 + Uvicorn |
| ORM / Migration | SQLAlchemy 2.1 (sync) + Alembic |
| Database | PostgreSQL 17 (driver psycopg 3) |
| Validate dữ liệu | Pydantic v2, pydantic-settings, python-dotenv |
| Xác thực | OAuth2 Password Flow + JWT (PyJWT), băm mật khẩu bằng bcrypt |
| Cache | Redis |
| Email (dev) | Mailpit (SMTP giả lập, có giao diện web) |
| Test | pytest + TestClient + SQLite in-memory + fakeredis |
| Triển khai | Docker + docker-compose |

---

## 1. Chạy nhanh bằng Docker (khuyên dùng)

```bash
cp .env.example .env                              # rồi đổi SECRET_KEY (xem hướng dẫn trong file)
docker compose up -d --build                      # app + PostgreSQL + Redis + Mailpit
docker compose exec app python -m scripts.seed    # tạo dữ liệu mẫu
```

| Địa chỉ | Dùng để |
|---|---|
| <http://localhost:8000/docs> | Swagger UI: thử API trực tiếp |
| <http://localhost:8000/redoc> | Tài liệu API dạng đọc |
| <http://localhost:8000/health> | Kiểm tra app và kết nối DB |
| <http://localhost:8025> | Mailpit: xem email thông báo comment |

Container `app` tự chạy `alembic upgrade head` trước khi khởi động server.

## 2. Chạy ở máy local (để dev)

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

docker compose up -d db redis mailpit   # chỉ bật hạ tầng
alembic upgrade head                    # tạo bảng
python -m scripts.seed                  # dữ liệu mẫu
uvicorn app.main:app --reload           # http://localhost:8000/docs
```

Đặt `DB_ECHO=true` trong `.env` để in mọi câu SQL ra log, rất tiện khi muốn thấy tận mắt N+1 query.

## 3. Tài khoản mẫu

Tất cả dùng chung mật khẩu **`Password123`**.

| Username | Vai trò |
|---|---|
| `admin` | Admin hệ thống, làm được mọi thứ |
| `alice` | PM của project **TaskHub Backend** (task 1–6) |
| `bob` | PM của project **TaskHub Mobile** (task 7–9) |
| `carol`, `dave` | Member, được assign một số task |

Đăng nhập trên Swagger: bấm nút **Authorize**, nhập username/password (hoặc email/password).

## 4. Chạy test & lint

```bash
pytest          # 72 test, khoảng 15 giây, KHÔNG cần Docker/PostgreSQL/Redis
pytest -v tests/test_tasks.py::test_register_login_and_create_task_flow   # integration test bắt buộc của đề
ruff check .    # lint (cấu hình trong pyproject.toml)
mypy            # kiểm tra kiểu cho app/ và scripts/
```

## 5. Cấu trúc thư mục

```
.
├── app/
│   ├── main.py              # Tạo app: CORS, middleware log, exception handler, gắn router
│   ├── config.py            # Đọc cấu hình từ .env (pydantic-settings)
│   ├── database.py          # engine, SessionLocal, Base, dependency get_db
│   ├── security.py          # bcrypt hash/verify, tạo/giải mã JWT
│   ├── dependencies.py      # get_current_user, phân quyền (verify_*), load resource, phân trang
│   ├── permissions.py       # Quy tắc phân quyền nghiệp vụ (hàm thuần True/False)
│   ├── core/                # Exception + handler, message lỗi, hằng số, error responses
│   ├── cache.py             # Redis cache (tự bỏ qua nếu Redis lỗi)
│   ├── logging_config.py    # Log ra console + file xoay vòng
│   ├── models/              # SQLAlchemy model = bảng trong DB
│   ├── schemas/             # Pydantic schema = hình dạng dữ liệu vào/ra API
│   ├── crud/                # Truy cập DB (query, eager loading, transaction)
│   ├── routers/             # Endpoint HTTP (APIRouter)
│   └── services/            # Nghiệp vụ assign / comment, gửi email (chạy ở background)
├── alembic/                 # Migration database
├── scripts/seed.py          # Dữ liệu mẫu
├── tests/                   # pytest
├── Dockerfile
└── docker-compose.yml
```

### Luồng xử lý một request

```
Client ──HTTP──▶ CORS middleware ──▶ Log middleware (request id, thời gian xử lý,
                                      bắt lỗi không lường trước -> 500 vẫn có CORS)
                                          │
                                          ▼
                     Router (app/routers)  ◀── Dependencies: get_db, get_current_user,
                     - validate input bằng      verify_project_manager, verify_task_editor,
                       Pydantic schema          Pagination, ... (lỗi -> AppException)
                     - kiểm tra quyền (permissions.py)
                                          │
                                          ▼
                     Service (app/services) - nghiệp vụ nhiều bước (assign, comment + email)
                                          │
                                          ▼
                     CRUD (app/crud) ──SQLAlchemy──▶ PostgreSQL
                                          │
                                          ▼
                     response_model (Pydantic) lọc field ──▶ JSON trả về client
                     BackgroundTasks (gửi email) chạy SAU khi đã trả response
```

## 6. Danh sách API

Quy ước:

- Các API **đọc** (GET) công khai, các API **ghi** đều cần đăng nhập. PM là người tạo project.
  Khi làm RBAC theo workspace (phụ lục đặc tả), quyền đọc sẽ theo membership và cần đăng nhập.
- Mọi API nằm dưới prefix `/api/v1`.
- Danh sách phân trang bằng `page` (từ 1) + `limit` (mặc định 20, tối đa 100),
  response có `total` và `pages` (tổng số trang).

| Method | Endpoint | Quyền | Mục đề |
|---|---|---|---|
| POST | `/api/v1/users/register` | Công khai | 4 |
| POST | `/api/v1/users/login` | Công khai | 4 |
| GET / PUT | `/api/v1/users/me` | Đã đăng nhập | 4 |
| GET | `/api/v1/users/me/bookmarks` | Đã đăng nhập (phân trang) | 5 |
| GET | `/api/v1/users/{username}/profile` | Công khai | 3 |
| GET | `/api/v1/users` | Admin | 5 |
| PATCH | `/api/v1/users/{user_id}` | Admin (đổi role, khóa tài khoản) | 5 |
| GET | `/api/v1/projects` | Công khai (phân trang) | 2 |
| POST | `/api/v1/projects` | Đã đăng nhập (người tạo thành PM) | 2 |
| GET | `/api/v1/projects/{project_id}` | Công khai (kèm tasks lồng nhau) | 2, 3 |
| PUT / DELETE | `/api/v1/projects/{project_id}` | PM / Admin | 5 |
| GET | `/api/v1/projects/{project_id}/tasks` | Công khai (lọc + phân trang) | 3, 5 |
| POST | `/api/v1/projects/{project_id}/tasks` | Đã đăng nhập | 3 |
| GET | `/api/v1/tasks?status=&priority=&project_id=&assignee_id=&q=` | Công khai (lọc + phân trang) | 5 |
| GET | `/api/v1/tasks/{task_id}` | Công khai | 3 |
| PUT | `/api/v1/tasks/{task_id}` | Người tạo / người được assign / PM / Admin | 6 |
| DELETE | `/api/v1/tasks/{task_id}` | Người tạo / PM / Admin | 6 |
| POST | `/api/v1/tasks/{task_id}/assign` | PM / Admin | 6 |
| POST / DELETE | `/api/v1/tasks/{task_id}/bookmark` | Đã đăng nhập | 5 |
| GET | `/api/v1/tasks/{task_id}/activities` | Công khai (phân trang) | 6 |
| GET / POST | `/api/v1/tasks/{task_id}/comments` | GET công khai (phân trang), POST cần đăng nhập (gửi email ngầm) | 6, 7 |
| PUT / DELETE | `/api/v1/tasks/{task_id}/comments/{comment_id}` | Tác giả / PM / Admin | 6 |
| GET | `/api/v1/tags` | Công khai (cache Redis) | 2, 7 |
| POST / DELETE | `/api/v1/tags`, `/api/v1/tags/{tag_id}` | Admin | 7 |
| GET | `/health` | Công khai | 8 |

Lỗi luôn trả về dạng `{"detail": "..."}`, mã lỗi của từng endpoint được document trên Swagger:

- `401`: chưa đăng nhập hoặc token sai/hết hạn.
- `403`: đã đăng nhập nhưng không đủ quyền.
- `404`: resource trên URL không tồn tại.
- `400`: body tham chiếu tới dữ liệu không tồn tại (tag_ids, assignee_id).
- `409`: trùng dữ liệu (username, email, tag).
- `422`: dữ liệu sai định dạng.
