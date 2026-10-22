"""Message lỗi trả về cho client, gom 1 chỗ để không gõ lệch giữa các router."""

# --- Chung ---
INTERNAL_SERVER_ERROR = "Internal server error"

# --- Auth ---
INVALID_CREDENTIALS = "Could not validate credentials"
INCORRECT_LOGIN = "Incorrect email or password"
INACTIVE_USER = "Inactive user"
ADMIN_REQUIRED = "Admin privileges required"
INVALID_REFRESH_TOKEN = "Invalid, expired or revoked refresh token"
WRONG_CURRENT_PASSWORD = "Current password is incorrect"
NEW_PASSWORD_SAME_AS_CURRENT = "New password must be different from the current password"

# --- User ---
USER_NOT_FOUND = "User not found"
EMAIL_TAKEN = "Email already registered"
ADMIN_CANNOT_DEMOTE_SELF = "Admins cannot demote or deactivate themselves"

# --- Workspace ---
WORKSPACE_NOT_FOUND = "Workspace not found"
WORKSPACE_ROLE_REQUIRED = "This action requires at least the {role} role in the workspace"
WORKSPACE_HAS_PROJECTS = "Workspace still has projects, delete them first"
MEMBER_NOT_FOUND = "Member not found"
ALREADY_MEMBER = "User is already a member of this workspace"
INVITEE_NOT_FOUND = "No active user with this email"
OWNER_MEMBERSHIP_LOCKED = "The workspace owner cannot be removed or change role"
OWNER_ROLE_NOT_ASSIGNABLE = "OWNER role cannot be assigned, a workspace has exactly one owner"

# --- Project ---
PROJECT_NOT_FOUND = "Project not found"
PROJECT_ARCHIVED = (
    "Project is archived: it is read-only together with its tasks and comments, unarchive it first"
)

# --- Task ---
TASK_NOT_FOUND = "Task not found"
TASK_DELETE_FORBIDDEN = "Only the task creator or the workspace owner can delete this task"
ASSIGNEE_NOT_EDITOR = "Assignee must be an active member with at least the EDITOR role"

# --- Comment ---
COMMENT_NOT_FOUND = "Comment not found"
COMMENT_MODIFY_FORBIDDEN = "Only the comment author or the workspace owner can modify this comment"

# --- Tag ---
TAG_NOT_FOUND = "Tag not found"
TAG_ALREADY_EXISTS = "Tag already exists"
TAG_IDS_NOT_FOUND = "Tag ids not found: {ids}"

# --- Validate input (schema) ---
FIELD_CANNOT_BE_NULL = "{field} cannot be null"
SKIP_PARAM_REMOVED = (
    "skip is no longer supported, use page (page N starts at item (N - 1) * limit)"
)
PASSWORD_TOO_LONG = "Password is too long (max {max_bytes} bytes)"
DUE_DATE_IN_PAST = "due_date cannot be in the past"
TITLE_MUST_BE_SINGLE_LINE = "title must not contain line breaks"
