"""Cache đơn giản trên Redis (lưu JSON).

Nguyên tắc: cache chỉ là lớp tăng tốc, KHÔNG được làm sập API.
Redis chưa cấu hình hoặc bị lỗi -> ghi log cảnh báo rồi đọc thẳng từ DB.
"""

import hashlib
import json
import logging
from collections.abc import Mapping
from typing import Any

import redis
from pydantic import BaseModel

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


def cache_get_text(key: str) -> str | None:
    """Đọc chuỗi đã lưu (vd JSON đã serialize sẵn). None nếu không có / Redis tắt / lỗi."""
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except redis.RedisError as exc:
        logger.warning("Redis GET %s failed: %s", key, exc)
        return None
    if isinstance(raw, bytes):  # client tạo với decode_responses=True nên thực tế luôn là str
        return raw.decode("utf-8")
    return raw


def cache_set_text(key: str, value: str, ttl: int) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)  # ex = TTL, tự hết hạn sau `ttl` giây
    except redis.RedisError as exc:
        logger.warning("Redis SET %s failed: %s", key, exc)


def cache_get(key: str) -> Any | None:
    raw = cache_get_text(key)
    return json.loads(raw) if raw is not None else None


def cache_set(key: str, value: Any, ttl: int) -> None:
    cache_set_text(key, json.dumps(value), ttl)


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


def cache_bump_versions(keys: Mapping[str, int | None]) -> None:
    """INCR nhiều key version (key -> TTL, None = không hết hạn) trong 1 lần gửi (pipeline).

    INCR thay vì xóa key dữ liệu: request đọc DB TRƯỚC khi dữ liệu đổi mà ghi cache SAU khi đã xóa
    key sẽ đưa dữ liệu cũ trở lại cache; với version, request đó chỉ ghi vào key của phiên bản cũ.
    1 pipeline cho mọi key: Redis chết thì chỉ chờ timeout 1 lần, không phải 1 lần cho mỗi key.
    """
    client = get_redis()
    if client is None or not keys:
        return
    try:
        with client.pipeline() as pipe:
            for key, ttl in keys.items():
                pipe.incr(key)
                if ttl is not None:
                    pipe.expire(key, ttl)
            pipe.execute()
    except redis.RedisError as exc:
        logger.warning("Redis INCR %s failed: %s", ", ".join(keys), exc)


def cache_bump_version(key: str, ttl: int | None = None) -> None:
    cache_bump_versions({key: ttl})


def schema_fingerprint(model: type[BaseModel]) -> str:
    """8 ký tự đầu SHA-256 của JSON schema, đưa vào key cache.

    Đổi hình dạng response (thêm / bỏ field, đổi kiểu, giá trị enum) thì đổi fingerprint -> đọc
    key mới: bản deploy mới không đọc phải dữ liệu cache theo hình dạng cũ (lỗi validate -> 500),
    kể cả lúc rolling deploy bản cũ và bản mới chạy song song.
    """
    schema = json.dumps(model.model_json_schema(), sort_keys=True)
    return hashlib.sha256(schema.encode("utf-8")).hexdigest()[:8]
