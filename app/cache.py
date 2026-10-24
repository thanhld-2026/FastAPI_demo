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
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
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


def cache_version(key: str) -> int | None:
    """Phiên bản hiện tại của 1 nhóm cache (0 nếu chưa có). None nếu Redis tắt / lỗi -> bỏ qua
    cache, đọc thẳng DB."""
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except redis.RedisError as exc:
        logger.warning("Redis GET %s failed: %s", key, exc)
        return None
    return int(raw) if raw is not None else 0


def cache_bump_version(key: str, ttl: int | None = None) -> None:
    """INCR phiên bản: key dữ liệu của phiên bản cũ không còn được đọc nữa, tự hết hạn theo TTL.

    Khác xóa key: request đọc DB TRƯỚC khi dữ liệu đổi mà ghi cache SAU khi đã xóa key sẽ đưa
    dữ liệu cũ trở lại cache. Với version, request đó chỉ ghi vào key của phiên bản cũ.
    """
    client = get_redis()
    if client is None:
        return
    try:
        with client.pipeline() as pipe:
            pipe.incr(key)
            if ttl is not None:
                pipe.expire(key, ttl)
            pipe.execute()
    except redis.RedisError as exc:
        logger.warning("Redis INCR %s failed: %s", key, exc)
