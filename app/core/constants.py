"""Hằng số dùng chung giữa model (độ dài cột trong DB) và schema (validate input).

Khai báo 1 chỗ để không bị lệch: sửa String(...) ở model mà quên max_length ở schema
thì input hợp lệ vẫn có thể bị DB từ chối.
"""

# --- User ---
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
EMAIL_MAX_LENGTH = 255
FULL_NAME_MAX_LENGTH = 100
BIO_MAX_LENGTH = 1000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # giới hạn của bcrypt, tính theo BYTES chứ không phải ký tự

# --- Project ---
PROJECT_NAME_MAX_LENGTH = 100

# --- Task ---
TASK_TITLE_MAX_LENGTH = 200
TASK_SEARCH_MAX_LENGTH = 100

# --- Tag ---
TAG_NAME_MAX_LENGTH = 30

# --- Pagination ---
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
