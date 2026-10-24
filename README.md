# TaskHub API

RESTful API quản lý **project** và **task** (giống Jira/Trello thu nhỏ), xây dựng bằng FastAPI. Đây là bài thực hành của khóa FastAPI, đi lần lượt qua 8 mục: setup, CRUD, quan hệ model, xác thực JWT, phân quyền, nghiệp vụ & transaction, testing / background task / cache, triển khai.

| Thành phần | Công nghệ |
|---|---|
| Web framework | FastAPI 0.146 + Uvicorn |
| ORM / Migration | SQLAlchemy 2.1 (sync) + Alembic |
| Database | PostgreSQL 17 (driver psycopg 3) |
| Validate dữ liệu | Pydantic v2, pydantic-settings, python-dotenv |
| Xác thực | OAuth2 Password Flow, JWT access token + refresh token (rotation, thu hồi được), bcrypt |
| Cache | Redis (danh sách task và danh sách label của từng project, cache-aside có version + TTL) |
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
| <http://localhost:8025> | Mailpit: xem email thông báo (comment mới, được giao task) |

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

| Email | Workspace **Backend Team** (project TaskHub Backend, task 1–6) | Workspace **Mobile Team** (project TaskHub Mobile, task 7–9) |
|---|---|---|
| `admin@example.com` | Admin hệ thống: làm được mọi thứ ở mọi workspace | |
| `alice@example.com` | OWNER | không phải thành viên |
| `bob@example.com` | VIEWER | OWNER |
| `carol@example.com`, `dave@example.com` | EDITOR | EDITOR |

Đăng nhập bằng **email** (theo đặc tả, user không có username). Trên Swagger bấm **Authorize**,
ô `username` của form OAuth2 nhập email (tên field do chuẩn OAuth2 quy định).

Phiên đăng nhập gồm 2 token:

- **Access token** (JWT, mặc định 15 phút): gửi trong header `Authorization: Bearer ...`.
  Không lưu DB nên không thu hồi được, vì vậy để sống ngắn.
- **Refresh token** (chuỗi ngẫu nhiên, mặc định 7 ngày): DB chỉ lưu SHA-256 của nó.
  `POST /api/v1/auth/refresh` đổi lấy cặp token mới, token cũ hết dùng được (rotation).
  Các token nối tiếp nhau tạo thành 1 chuỗi = 1 phiên đăng nhập trên 1 thiết bị.
  Token cũ bị gửi lại sau thời gian ân hạn (`REFRESH_TOKEN_REUSE_GRACE_SECONDS`, mặc định 10 giây)
  thì coi như bị lộ: **cả chuỗi của phiên đó** bị thu hồi, phiên khác không ảnh hưởng.
  Gửi lại trong thời gian ân hạn (retry, 2 tab cùng refresh) chỉ nhận 401.
- Logout (kể cả bằng token cũ đã bị đổi) kết thúc cả phiên đó. Đổi mật khẩu thu hồi mọi phiên
  và trả cặp token mới cho thiết bị hiện tại. Admin khóa tài khoản cũng thu hồi mọi phiên.
- Refresh / logout / đổi mật khẩu / khóa tài khoản của cùng 1 user chạy tuần tự (khóa dòng user).
- Access token có claim `type: "access"`: JWT khác ký cùng `SECRET_KEY` không dùng thay được.
- Chưa có rate limit cho login / refresh / đổi mật khẩu (chống dò mật khẩu): dự định làm sau bằng
  Redis (đếm số lần theo IP + email trong 1 khoảng thời gian, quá ngưỡng trả `429`).

## 4. Chạy test & lint

```bash
pytest          # 161 test (+9 test PostgreSQL), khoảng 15 giây, KHÔNG cần Docker/PostgreSQL/Redis
pytest -v tests/test_tasks.py::test_register_login_and_create_task_flow   # integration test bắt buộc của đề
# Test khóa dòng (FOR SHARE / FOR UPDATE) cần PostgreSQL thật, DB rỗng dành riêng cho test:
# (test xóa / tạo lại toàn bộ bảng nên tên DB bắt buộc kết thúc bằng _test, nếu không test dừng ngay)
TEST_POSTGRES_URL=postgresql+psycopg://taskhub:taskhub@localhost:5432/taskhub_test pytest -m postgres
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
│   ├── security.py          # bcrypt hash/verify, tạo/giải mã JWT, tạo/hash refresh token
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
                     - validate input bằng      project_access(role), task_access(role),
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

- Mọi API (trừ register / login / refresh / logout, `/health`) cần đăng nhập. Dữ liệu nằm trong
  **workspace**; quyền đi theo role trong workspace (RBAC, bảng quyền ở `app/permissions.py`):
  - `VIEWER`: đọc mọi thứ trong workspace, bookmark task.
  - `EDITOR`: + tạo / sửa / assign task, comment; xóa task / sửa, xóa comment **của mình**.
  - `OWNER` (người tạo workspace, mỗi workspace đúng 1 người, DB chặn bằng partial unique index;
    chuyển được cho thành viên khác): + quản lý project, thành viên, workspace, xóa task / comment
    của người khác.
  - Admin hệ thống làm được mọi thứ ở mọi workspace.
- Không phải thành viên → `404` (không lộ resource có tồn tại hay không); là thành viên nhưng role
  không đủ → `403`. Thứ tự lỗi: 401 → 404 → 409 (project đã archive) → 403.
- Chỉ giao task cho thành viên từ `EDITOR` trở lên. Thành viên rời / bị xóa khỏi workspace hoặc
  bị hạ xuống `VIEWER` thì task của họ trong các project `ACTIVE` được bỏ assign (có ghi activity);
  project đã archive giữ nguyên. Email báo comment chỉ gửi cho người còn trong workspace.
- Mọi API nằm dưới prefix `/api/v1`.
- Danh sách phân trang bằng `page` (1 tới 10 000) + `limit` (mặc định 20, tối đa 100),
  response có `total` và `pages` (tổng số trang, tối thiểu 1). `page` vượt quá `pages` trả
  `items` rỗng. Tham số cũ `skip` bị từ chối (422) để client cũ không âm thầm nhận mãi trang 1.
- Task: status `TODO` / `IN_PROGRESS` / `IN_REVIEW` / `DONE`, priority `LOW` / `MEDIUM` / `HIGH` / `URGENT`.
- Label thuộc từng project (tên chỉ gồm chữ thường, số, gạch ngang như tag cũ, chữ hoa tự đổi
  thành chữ thường; không trùng trong project; màu hex), chỉ gắn
  được label của đúng project chứa task. Gắn / gỡ label cập nhật `updated_at` của task và ghi
  activity riêng `label_added` / `label_removed` (FE lọc được); xóa label thì ghi `label_removed`
  cho từng task đang dùng nó.
  Danh sách label được cache Redis theo project, có version: thêm / sửa / xóa label (hoặc xóa
  project) thì tăng version của project đó, cache cũ không bao giờ được đọc lại.
- `GET /projects/{id}/tasks` được cache Redis theo project + từng tổ hợp filter / trang (TTL
  `TASKS_CACHE_TTL`, mặc định 60 giây, header `X-Cache`). Cache tự làm mới sau mỗi commit làm đổi
  danh sách task của project (tạo / sửa / xóa / assign task, gắn / gỡ label, sửa / xóa label, user
  đổi tên, thành viên rời workspace...) nhờ event của SQLAlchemy Session (`app/services/task_cache.py`);
  comment / bookmark không làm mới. Kiểm tra quyền chạy trước khi đọc cache.
- Được giao task (assign) thì người được giao nhận email (chạy ngầm). Không gửi khi tự giao cho
  mình, giao lại đúng người đang làm hoặc bỏ assign.
- Project: `ACTIVE` / `ARCHIVED`. Chỉ project `ACTIVE` mới ghi được: project đã archive thì chính
  project, task, comment và label bên trong chỉ đọc được (mọi thao tác ghi, kể cả sửa / xóa project,
  trả `409`), OWNER / Admin unarchive để mở lại. Ngoại lệ có chủ đích: bookmark (dữ liệu cá nhân).
- Cột "Mục đề": số mục của tutorial; `PL n` là feature n trong phụ lục đặc tả sample app.

| Method | Endpoint | Quyền | Mục đề |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Công khai | 4 |
| POST | `/api/v1/auth/login` | Công khai (trả access + refresh token) | 4, PL 1 |
| POST | `/api/v1/auth/refresh` | Có refresh token hợp lệ | PL 1 |
| POST | `/api/v1/auth/logout` | Có refresh token (idempotent, 204) | PL 1 |
| GET / PATCH | `/api/v1/users/me` | Đã đăng nhập | 4, PL 2 |
| PUT | `/api/v1/users/me/password` | Đã đăng nhập, cần mật khẩu hiện tại (trả cặp token mới) | PL 2 |
| GET | `/api/v1/users/me/bookmarks` | Đã đăng nhập (phân trang) | 5 |
| GET | `/api/v1/users/{user_id}/profile` | Đã đăng nhập (chỉ hiện dữ liệu ở workspace chung) | 3 |
| GET | `/api/v1/users` | Admin | 5 |
| PATCH | `/api/v1/users/{user_id}` | Admin (đổi role, khóa tài khoản) | 5 |
| POST | `/api/v1/workspaces` | Đã đăng nhập (người tạo là OWNER) | PL 3 |
| GET | `/api/v1/workspaces` | Workspace tôi là thành viên (admin: tất cả) | PL 3 |
| GET | `/api/v1/workspaces/{workspace_id}` | VIEWER (kèm danh sách thành viên) | PL 3 |
| PATCH / DELETE | `/api/v1/workspaces/{workspace_id}` | OWNER (xóa: phải hết project, nếu không 409) | PL 3 |
| POST | `/api/v1/workspaces/{workspace_id}/members` | OWNER, mời theo email, role EDITOR / VIEWER | PL 3 |
| PATCH | `/api/v1/workspaces/{workspace_id}/members/{user_id}` | OWNER, đổi role | PL 3 |
| DELETE | `/api/v1/workspaces/{workspace_id}/members/{user_id}` | OWNER, hoặc tự rời workspace | PL 3 |
| POST | `/api/v1/workspaces/{workspace_id}/transfer-ownership` | OWNER / Admin, chuyển cho 1 thành viên đang hoạt động (owner cũ thành EDITOR) | PL 3 |
| POST | `/api/v1/workspaces/{workspace_id}/projects` | OWNER | 2, PL 4 |
| GET | `/api/v1/projects?status=&workspace_id=` | Project trong workspace của tôi (lọc + phân trang) | 2, PL 4 |
| GET | `/api/v1/projects/{project_id}` | VIEWER (kèm tasks lồng nhau) | 2, 3 |
| PUT / DELETE | `/api/v1/projects/{project_id}` | OWNER | 5, PL 4 |
| POST | `/api/v1/projects/{project_id}/archive`, `.../unarchive` | OWNER (idempotent) | PL 4 |
| GET | `/api/v1/projects/{project_id}/tasks?status=&priority=&assignee_id=` | VIEWER (lọc + phân trang, cache Redis, header `X-Cache`) | 3, 5, PL 8, 9 |
| POST | `/api/v1/projects/{project_id}/tasks` | EDITOR | 3 |
| GET | `/api/v1/tasks?status=&priority=&project_id=&assignee_id=&q=` | Task trong workspace của tôi (lọc + phân trang) | 5 |
| GET | `/api/v1/tasks/{task_id}` | VIEWER | 3 |
| PUT | `/api/v1/tasks/{task_id}` | EDITOR | 6 |
| DELETE | `/api/v1/tasks/{task_id}` | Người tạo (EDITOR) / OWNER | 6 |
| POST | `/api/v1/tasks/{task_id}/assign` | EDITOR (người được giao nhận email ngầm) | 6, PL 10 |
| POST / DELETE | `/api/v1/tasks/{task_id}/bookmark` | VIEWER | 5 |
| GET | `/api/v1/tasks/{task_id}/activities` | VIEWER (phân trang) | 6 |
| GET / POST | `/api/v1/tasks/{task_id}/comments` | GET: VIEWER (phân trang), POST: EDITOR (gửi email ngầm) | 6, 7 |
| PUT / DELETE | `/api/v1/tasks/{task_id}/comments/{comment_id}` | Tác giả (EDITOR) / OWNER | 6 |
| GET | `/api/v1/projects/{project_id}/labels` | VIEWER (cache Redis, header `X-Cache`) | 2, 7, PL 6 |
| POST | `/api/v1/projects/{project_id}/labels` | EDITOR (tên không trùng trong project) | PL 6 |
| PATCH / DELETE | `/api/v1/labels/{label_id}` | EDITOR (xóa: tự gỡ khỏi các task) | PL 6 |
| POST / DELETE | `/api/v1/tasks/{task_id}/labels/{label_id}` | EDITOR, label cùng project (idempotent) | PL 6 |
| GET | `/health` | Công khai | 8 |

Lỗi luôn trả về dạng `{"detail": "..."}`, mã lỗi của từng endpoint được document trên Swagger:

- `401`: chưa đăng nhập hoặc token sai/hết hạn.
- `403`: là thành viên nhưng role không đủ (hoặc tài khoản bị khóa).
- `404`: resource trên URL không tồn tại, hoặc không phải thành viên workspace chứa nó.
- `400`: body tham chiếu tới dữ liệu không tồn tại (label_ids, assignee_id, email được mời).
- `409`: trùng dữ liệu (email, tên label, thành viên) hoặc xung đột trạng thái
  (project đã archive, xóa workspace còn project).
- `422`: dữ liệu sai định dạng.

Giới hạn / quyết định có chủ đích:

- Mời thành viên theo email là thêm thẳng (không cần người được mời đồng ý, họ tự rời được), và
  ai tạo workspace cũng biết được 1 email đã đăng ký hay chưa (400 khác 201). Chấp nhận trong phạm vi
  bài thực hành; bản đầy đủ cần lời mời chờ chấp nhận + cùng 1 response cho mọi email.
- Quy tắc "label phải cùng project với task" mới được kiểm tra trong code, DB chưa chặn (cần thêm
  `project_id` vào `task_labels` + khóa ngoại kép, xem `app/models/associations.py`).
