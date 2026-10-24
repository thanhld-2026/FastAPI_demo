"""Gửi email qua SMTP. Các hàm ở đây được chạy NGẦM bằng FastAPI BackgroundTasks.

Lưu ý khi viết background task:
- Chỉ truyền dữ liệu thuần (str, int, list...), KHÔNG truyền SQLAlchemy object hay Session:
  khi task chạy thì response đã trả về và session của request đã đóng.
- Tự bắt lỗi và ghi log: lỗi ở đây không còn trả về được cho client.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("[email disabled] to=%s subject=%r", to, subject)
        return

    try:
        # Dựng message cũng nằm trong try: header không hợp lệ (vd subject có ký tự xuống dòng)
        # ném ValueError, nếu để ngoài thì background task chết mà không có log
        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
        ) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        logger.info("Email sent to=%s subject=%r", to, subject)
    except (smtplib.SMTPException, OSError, ValueError):
        logger.exception("Failed to send email to=%s subject=%r", to, subject)


def notify_new_comment(
    recipients: list[str], *, task_id: int, task_title: str, commenter: str, content: str
) -> None:
    """Báo cho người tạo task và người được assign khi có comment mới."""
    subject = f"[TaskHub] {commenter} commented on task #{task_id}: {task_title}"
    body = (
        f"{commenter} vừa bình luận vào task #{task_id} \"{task_title}\":\n\n"
        f"{content}\n\n"
        f"-- TaskHub"
    )
    for recipient in recipients:
        send_email(recipient, subject, body)


def notify_task_assigned(
    recipient: str,
    *,
    task_id: int,
    task_title: str,
    project_name: str,
    priority: str,
    due_date: str | None,
    assigner: str,
) -> None:
    """Báo cho người vừa được giao task (phụ lục feature 10)."""
    subject = f"[TaskHub] {assigner} assigned you task #{task_id}: {task_title}"
    body = (
        f"{assigner} vừa giao cho bạn task #{task_id} \"{task_title}\".\n\n"
        f"Project: {project_name}\n"
        f"Priority: {priority}\n"
        f"Due date: {due_date or '-'}\n\n"
        f"-- TaskHub"
    )
    send_email(recipient, subject, body)
