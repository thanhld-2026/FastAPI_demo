"""Message lỗi trả về cho client, gom 1 chỗ để không gõ lệch giữa các router."""

# --- Auth ---
INVALID_CREDENTIALS = "Could not validate credentials"
INCORRECT_LOGIN = "Incorrect username or password"
INACTIVE_USER = "Inactive user"
ADMIN_REQUIRED = "Admin privileges required"

# --- User ---
USER_NOT_FOUND = "User not found"
USERNAME_TAKEN = "Username already registered"
EMAIL_TAKEN = "Email already registered"
USERNAME_OR_EMAIL_TAKEN = "Username or email already registered"
ADMIN_CANNOT_DEMOTE_SELF = "Admins cannot demote or deactivate themselves"

# --- Project ---
PROJECT_NOT_FOUND = "Project not found"
PROJECT_MANAGER_REQUIRED = "Only the project manager or an admin can perform this action"

# --- Task ---
TASK_NOT_FOUND = "Task not found"
TASK_EDIT_FORBIDDEN = "Not allowed to edit this task"
TASK_DELETE_FORBIDDEN = "Not allowed to delete this task"

# --- Tag ---
TAG_NOT_FOUND = "Tag not found"
TAG_ALREADY_EXISTS = "Tag already exists"
TAG_IDS_NOT_FOUND = "Tag ids not found: {ids}"

# --- Validate input (schema) ---
FIELD_CANNOT_BE_NULL = "{field} cannot be null"
PASSWORD_TOO_LONG = "Password is too long (max {max_bytes} bytes)"
