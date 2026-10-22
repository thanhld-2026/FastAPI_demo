"""Tạo dữ liệu mẫu để demo.

Chạy (sau khi đã `alembic upgrade head`):
    python -m scripts.seed                          # chạy ở máy local
    docker compose exec app python -m scripts.seed  # chạy trong container

Chạy lại nhiều lần không bị trùng: nếu đã có user "admin" thì bỏ qua.
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    ActivityAction,
    Comment,
    Label,
    Project,
    Task,
    TaskActivity,
    TaskPriority,
    TaskStatus,
    User,
    UserRole,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from app.security import hash_password

PASSWORD = "Password123"

USERS = [
    # tên ngắn (email = <tên>@example.com), full_name, role
    ("admin", "System Admin", UserRole.ADMIN),
    ("alice", "Alice Nguyen", UserRole.MEMBER),  # OWNER của workspace "Backend Team"
    ("bob", "Bob Tran", UserRole.MEMBER),  # OWNER "Mobile Team", VIEWER ở "Backend Team"
    ("carol", "Carol Le", UserRole.MEMBER),  # EDITOR ở cả 2 workspace
    ("dave", "Dave Pham", UserRole.MEMBER),  # EDITOR ở cả 2 workspace
]

WORKSPACES = [
    # tên workspace, owner, các thành viên khác (tên ngắn, role)
    ("Backend Team", "alice", [("carol", "EDITOR"), ("dave", "EDITOR"), ("bob", "VIEWER")]),
    ("Mobile Team", "bob", [("carol", "EDITOR"), ("dave", "EDITOR")]),
]

# Label theo từng project: tên -> màu
LABEL_COLORS = {
    "backend": "#2563eb",
    "frontend": "#9333ea",
    "mobile": "#0891b2",
    "bug": "#dc2626",
    "feature": "#16a34a",
    "docs": "#6b7280",
    "urgent": "#ea580c",
}


def seed() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == "admin@example.com")):
            print("Seed data already exists -> skip.")
            return

        users = {
            name: User(
                email=f"{name}@example.com",
                full_name=full_name,
                role=role,
                hashed_password=hash_password(PASSWORD),
            )
            for name, full_name, role in USERS
        }
        db.add_all(users.values())
        # flush: gửi INSERT xuống DB (có id) nhưng CHƯA commit -> vẫn chung 1 transaction.
        # Flush từng bước để id sinh ra theo đúng thứ tự khai báo, dễ theo dõi khi demo.
        db.flush()

        workspaces = []
        for ws_name, owner, others in WORKSPACES:
            workspace = Workspace(name=ws_name, owner=users[owner])
            workspace.members.append(WorkspaceMember(user=users[owner], role=WorkspaceRole.OWNER))
            for name, role in others:
                workspace.members.append(WorkspaceMember(user=users[name], role=WorkspaceRole(role)))
            workspaces.append(workspace)
        db.add_all(workspaces)
        db.flush()

        backend = Project(
            name="TaskHub Backend",
            description="RESTful API cho TaskHub, xây dựng bằng FastAPI",
            workspace=workspaces[0],
            creator=users["alice"],
        )
        mobile = Project(
            name="TaskHub Mobile",
            description="Ứng dụng mobile gọi TaskHub API",
            workspace=workspaces[1],
            creator=users["bob"],
        )
        db.add_all([backend, mobile])
        db.flush()

        today = date.today()
        task_specs = [
            # project, title, status, priority, creator, assignee, labels, due_in_days
            (backend, "Thiết kế database & ERD", TaskStatus.DONE, TaskPriority.HIGH, "alice", "carol", ["backend", "docs"], -7),
            (backend, "API đăng ký / đăng nhập JWT", TaskStatus.DONE, TaskPriority.HIGH, "alice", "carol", ["backend", "feature"], -3),
            (backend, "Phân quyền theo workspace (RBAC)", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, "alice", "dave", ["backend", "feature"], 2),
            (backend, "Cache danh sách label bằng Redis", TaskStatus.TODO, TaskPriority.MEDIUM, "carol", None, ["backend"], 5),
            (backend, "Viết integration test", TaskStatus.IN_REVIEW, TaskPriority.MEDIUM, "alice", "dave", ["backend", "docs"], 7),
            (backend, "Fix lỗi 500 khi token hết hạn", TaskStatus.TODO, TaskPriority.HIGH, "dave", None, ["bug", "urgent"], 1),
            (mobile, "Màn hình đăng nhập", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, "bob", "carol", ["mobile", "frontend"], 3),
            (mobile, "Danh sách task theo project", TaskStatus.TODO, TaskPriority.MEDIUM, "bob", None, ["mobile", "feature"], 10),
            (mobile, "Push notification khi có comment", TaskStatus.TODO, TaskPriority.LOW, "bob", "dave", ["mobile"], 14),
        ]

        # Mỗi project chỉ có các label mà task của nó dùng tới
        labels: dict[tuple[int, str], Label] = {}
        for project, *_, label_names, _ in task_specs:
            for name in label_names:
                if (project.id, name) not in labels:
                    labels[project.id, name] = Label(
                        project=project, name=name, color=LABEL_COLORS[name]
                    )
        db.add_all(labels.values())
        db.flush()

        tasks: list[Task] = []
        for project, title, status, priority, creator, assignee, label_names, due_in in task_specs:
            task = Task(
                project=project,
                title=title,
                status=status,
                priority=priority,
                creator=users[creator],
                assignee=users[assignee] if assignee else None,
                labels=[labels[project.id, name] for name in label_names],
                due_date=today + timedelta(days=due_in),
            )
            task.activities.append(TaskActivity(actor=users[creator], action=ActivityAction.CREATED))
            if assignee:
                task.activities.append(
                    TaskActivity(
                        actor=project.workspace.owner,
                        action=ActivityAction.ASSIGNED,
                        detail=f"assigned to {assignee}",
                    )
                )
            db.add(task)
            db.flush()
            tasks.append(task)

        comments = [
            (tasks[2], "carol", "Mình gợi ý tách logic phân quyền ra file permissions.py cho dễ test."),
            (tasks[2], "alice", "Đồng ý, nhớ thêm test cho case member không được assign nhé."),
            (tasks[6], "bob", "Design màn hình đã có trên Figma, Carol check giúp mình."),
        ]
        for task, author, content in comments:
            task.comments.append(Comment(author=users[author], content=content))
            task.activities.append(TaskActivity(actor=users[author], action=ActivityAction.COMMENTED))

        users["carol"].bookmarked_tasks.extend([tasks[2], tasks[5]])

        db.commit()  # toàn bộ dữ liệu mẫu được lưu trong 1 transaction

        print(f"Seed data created. Accounts (password: {PASSWORD}):")
        for name, _, role in USERS:
            print(f"  - {name + '@example.com':<18} ({role.value})")
        for ws_name, owner, others in WORKSPACES:
            members = ", ".join(f"{name} {role}" for name, role in others)
            print(f"Workspace {ws_name!r}: {owner} OWNER, {members}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
