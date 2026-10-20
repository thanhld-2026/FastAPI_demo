"""Cấu hình logging: ghi ra console và file (tự xoay vòng khi file quá lớn)."""

import logging.config
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    handlers: dict[str, dict] = {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    }
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": log_file,
            "maxBytes": 5 * 1024 * 1024,  # 5 MB / file
            "backupCount": 3,  # giữ tối đa app.log.1 ... app.log.3
            "encoding": "utf-8",
        }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": LOG_FORMAT}},
            "handlers": handlers,
            "root": {"level": level.upper(), "handlers": list(handlers)},
            "loggers": {
                # Access log đã do middleware của app ghi (kèm request id + thời gian xử lý)
                # nên tắt access log mặc định của uvicorn để tránh trùng lặp.
                "uvicorn.access": {"level": "WARNING", "propagate": False},
            },
        }
    )
