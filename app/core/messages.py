"""Message lỗi trả về cho client, gom 1 chỗ để không gõ lệch giữa các router."""

# --- Chung ---
INTERNAL_SERVER_ERROR = "Internal server error"

# --- Auth ---
INVALID_CREDENTIALS = "Could not validate credentials"
INCORRECT_LOGIN = "Incorrect username or password"
INACTIVE_USER = "Inactive user"
ADMIN_REQUIRED = "Admin privileges required"
INVALID_REFRESH_TOKEN = "Invalid, expired or revoked refresh token"

# --- User ---
USER_NOT_FOUND = "User not found"
USERNAME_TAKEN = "Username already registered"
EMAIL_TAKEN = "Email already registered"
USERNAME_OR_EMAIL_TAKEN = "Username or email already registered"
ADMIN_CANNOT_DEMOTE_SELF = "Admins cannot demote or deactivate themselves"

# --- Project ---
PROJECT_NOT_FOUND = "Project not found"
PROJECT_MANAGER_REQUIRED = "Only the project manager or an admin can perform this action"
PROJECT_ARCHIVED = "Project is archived, its tasks and comments are read-only"

# --- Task ---
TASK_NOT_FOUND = "Task not found"
TASK_EDIT_FORBIDDEN = "Not allowed to edit this task"
TASK_DELETE_FORBIDDEN = "Not allowed to delete this task"
TASK_ASSIGN_FORBIDDEN = "Only the project manager or an admin can assign tasks"
ASSIGNEE_NOT_FOUND = "Assignee not found or inactive"

# --- Comment ---
COMMENT_NOT_FOUND = "Comment not found"
COMMENT_MODIFY_FORBIDDEN = (
    "Only the comment author, the project manager or an admin can modify this comment"
)

# --- Tag ---
TAG_NOT_FOUND = "Tag not found"
TAG_ALREADY_EXISTS = "Tag already exists"
TAG_IDS_NOT_FOUND = "Tag ids not found: {ids}"

# --- Validate input (schema) ---
FIELD_CANNOT_BE_NULL = "{field} cannot be null"
SKIP_PARAM_REMOVED = "skip is no longer supported, use page instead (page = skip / limit + 1)"
PASSWORD_TOO_LONG = "Password is too long (max {max_bytes} bytes)"
DUE_DATE_IN_PAST = "due_date cannot be in the past"
TITLE_MUST_BE_SINGLE_LINE = "title must not contain line breaks"
