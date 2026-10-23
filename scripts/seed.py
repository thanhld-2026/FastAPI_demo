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
    Project,
    Tag,
    Task,
    TaskActivity,
    TaskPriority,
    TaskStatus,
    User,
    UserRole,
)
from app.security import hash_password

PASSWORD = "Password123"

USERS = [
    # tên ngắn (email = <tên>@example.com), full_name, role
    ("admin", "System Admin", UserRole.ADMIN),
    ("alice", "Alice Nguyen", UserRole.MEMBER),  # PM của project "TaskHub Backend"
    ("bob", "Bob Tran", UserRole.MEMBER),  # PM của project "TaskHub Mobile"
    ("carol", "Carol Le", UserRole.MEMBER),
    ("dave", "Dave Pham", UserRole.MEMBER),
]

TAGS = ["backend", "frontend", "mobile", "bug", "feature", "docs", "urgent"]


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
        tags = {name: Tag(name=name) for name in TAGS}
        db.add_all([*users.values(), *tags.values()])
        # flush: gửi INSERT xuống DB (có id) nhưng CHƯA commit -> vẫn chung 1 transaction.
        # Flush từng bước để id sinh ra theo đúng thứ tự khai báo, dễ theo dõi khi demo.
        db.flush()

        backend = Project(
            name="TaskHub Backend",
            description="RESTful API cho TaskHub, xây dựng bằng FastAPI",
            owner=users["alice"],
        )
        mobile = Project(
            name="TaskHub Mobile",
            description="Ứng dụng mobile gọi TaskHub API",
            owner=users["bob"],
        )
        db.add_all([backend, mobile])
        db.flush()

        today = date.today()
        task_specs = [
            # project, title, status, priority, creator, assignee, tags, due_in_days
            (backend, "Thiết kế database & ERD", TaskStatus.DONE, TaskPriority.HIGH, "alice", "carol", ["backend", "docs"], -7),
            (backend, "API đăng ký / đăng nhập JWT", TaskStatus.DONE, TaskPriority.HIGH, "alice", "carol", ["backend", "feature"], -3),
            (backend, "Phân quyền PM / Admin", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, "alice", "dave", ["backend", "feature"], 2),
            (backend, "Cache danh sách tag bằng Redis", TaskStatus.TODO, TaskPriority.MEDIUM, "carol", None, ["backend"], 5),
            (backend, "Viết integration test", TaskStatus.IN_REVIEW, TaskPriority.MEDIUM, "alice", "dave", ["backend", "docs"], 7),
            (backend, "Fix lỗi 500 khi token hết hạn", TaskStatus.TODO, TaskPriority.HIGH, "dave", None, ["bug", "urgent"], 1),
            (mobile, "Màn hình đăng nhập", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, "bob", "carol", ["mobile", "frontend"], 3),
            (mobile, "Danh sách task theo project", TaskStatus.TODO, TaskPriority.MEDIUM, "bob", None, ["mobile", "feature"], 10),
            (mobile, "Push notification khi có comment", TaskStatus.TODO, TaskPriority.LOW, "bob", "dave", ["mobile"], 14),
        ]

        tasks: list[Task] = []
        for project, title, status, priority, creator, assignee, tag_names, due_in in task_specs:
            task = Task(
                project=project,
                title=title,
                status=status,
                priority=priority,
                creator=users[creator],
                assignee=users[assignee] if assignee else None,
                tags=[tags[name] for name in tag_names],
                due_date=today + timedelta(days=due_in),
            )
            task.activities.append(TaskActivity(actor=users[creator], action=ActivityAction.CREATED))
            if assignee:
                task.activities.append(
                    TaskActivity(
                        actor=project.owner,
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
    finally:
        db.close()


if __name__ == "__main__":
    seed()
