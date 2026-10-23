"""Hằng số dùng chung giữa model (độ dài cột trong DB) và schema (validate input).

Khai báo 1 chỗ để không bị lệch: sửa String(...) ở model mà quên max_length ở schema
thì input hợp lệ vẫn có thể bị DB từ chối.
"""

# --- API ---
# Thay đổi không tương thích ngược sau này thì thêm /api/v2 chạy song song với v1.
# (URL cũ không có version `/api/...` đã bỏ hẳn, gọi vào trả 404.)
API_V1_PREFIX = "/api/v1"

# --- Chuỗi bắt buộc: không được rỗng (sau khi đã cắt khoảng trắng 2 đầu) ---
REQUIRED_TEXT_MIN_LENGTH = 1

# --- User ---
EMAIL_MAX_LENGTH = 255
PASSWORD_HASH_MAX_LENGTH = 255  # chuỗi bcrypt dài 60, để dư cho thuật toán khác
FULL_NAME_MAX_LENGTH = 100
BIO_MAX_LENGTH = 1000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # giới hạn của bcrypt, tính theo BYTES chứ không phải ký tự

# --- Refresh token ---
REFRESH_TOKEN_BYTES = 32  # độ dài ngẫu nhiên trước khi encode base64 (~43 ký tự)
REFRESH_TOKEN_MAX_LENGTH = 128  # giới hạn input client gửi lên
TOKEN_HASH_LENGTH = 64  # SHA-256 dạng hex

# --- Workspace ---
WORKSPACE_NAME_MAX_LENGTH = 100

# --- Project ---
PROJECT_NAME_MAX_LENGTH = 100

# --- Task ---
TASK_TITLE_MAX_LENGTH = 200
TASK_SEARCH_MAX_LENGTH = 100

# --- Activity ---
ACTIVITY_DETAIL_MAX_LENGTH = 255

# --- Comment ---
COMMENT_MAX_LENGTH = 2000

# --- Label (theo từng project) ---
LABEL_NAME_MAX_LENGTH = 30
# Giống tag cũ: chữ thường, số, gạch ngang (vd "bug", "needs-review");
# không khoảng trắng, không xuống dòng
LABEL_NAME_PATTERN = r"^[a-z0-9-]+$"
LABEL_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"  # mã màu hex, vd #EF4444
LABEL_COLOR_LENGTH = 7
DEFAULT_LABEL_COLOR = "#6b7280"

# --- Request id (header X-Request-ID) ---
# Chỉ nhận id client gửi lên nếu đúng định dạng, không thì tự sinh (tránh làm bẩn log)
REQUEST_ID_PATTERN = r"[A-Za-z0-9._-]{1,64}"

# --- Pagination ---
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
# Chặn page quá lớn: offset = (page - 1) * limit vượt kiểu số nguyên của DB -> 500,
# và OFFSET rất lớn bắt DB duyệt qua hàng triệu dòng chỉ để bỏ đi
MAX_PAGE = 10_000
