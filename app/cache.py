"""Cache đơn giản trên Redis (lưu JSON).

Nguyên tắc: cache chỉ là lớp tăng tốc, KHÔNG được làm sập API.
Redis chưa cấu hình hoặc bị lỗi -> ghi log cảnh báo rồi đọc thẳng từ DB.
"""

import json
import logging
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _client
    if not settings.REDIS_URL:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,  # Redis chết -> fail nhanh, không treo request
            socket_timeout=1,
        )
    return _client


def cache_get(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except redis.RedisError as exc:
        logger.warning("Redis GET %s failed: %s", key, exc)
        return None
    return json.loads(raw) if raw is not None else None


def cache_set(key: str, value: Any, ttl: int) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl)  # ex = TTL, tự hết hạn sau `ttl` giây
    except redis.RedisError as exc:
        logger.warning("Redis SET %s failed: %s", key, exc)


def cache_delete(key: str) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(key)
    except redis.RedisError as exc:
        logger.warning("Redis DELETE %s failed: %s", key, exc)
