"""Hằng số dùng chung giữa model (độ dài cột trong DB) và schema (validate input).

Khai báo 1 chỗ để không bị lệch: sửa String(...) ở model mà quên max_length ở schema
thì input hợp lệ vẫn có thể bị DB từ chối.
"""

# --- User ---
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
EMAIL_MAX_LENGTH = 255
PASSWORD_HASH_MAX_LENGTH = 255  # chuỗi bcrypt dài 60, để dư cho thuật toán khác
FULL_NAME_MAX_LENGTH = 100
BIO_MAX_LENGTH = 1000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # giới hạn của bcrypt, tính theo BYTES chứ không phải ký tự

# --- Project ---
PROJECT_NAME_MAX_LENGTH = 100

# --- Task ---
TASK_TITLE_MAX_LENGTH = 200
TASK_SEARCH_MAX_LENGTH = 100

# --- Activity ---
ACTIVITY_DETAIL_MAX_LENGTH = 255

# --- Comment ---
COMMENT_MAX_LENGTH = 2000

# --- Tag ---
TAG_NAME_MAX_LENGTH = 30

# --- Request id (header X-Request-ID) ---
# Chỉ nhận id client gửi lên nếu đúng định dạng, không thì tự sinh (tránh làm bẩn log)
REQUEST_ID_PATTERN = r"[A-Za-z0-9._-]{1,64}"

# --- Pagination ---
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
