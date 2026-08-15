"""Redis 缓存封装：结构化查询结果缓存（Cache-Aside）。

Redis 不可用时静默降级（读不到就查库，写不进就跳过），不影响主流程。
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal

import redis

from app.core.config import REDIS_URL, STRUCTURED_CACHE_TTL

logger = logging.getLogger(__name__)

VERSION_KEY = "structured:version"


def _json_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable"
    )


class RedisCache:
    def __init__(self) -> None:
        self._client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def get_version(self) -> int:
        """当前数据版本号；Redis 不可用时返回 0（退化到无版本隔离）。"""
        try:
            raw = self._client.get(VERSION_KEY)
            return int(raw) if raw else 0
        except redis.RedisError as exc:
            logger.warning("Redis get_version failed: %s", exc)
            return 0

    def bump_version(self) -> None:
        """数据重建后调用，使所有旧缓存失效。"""
        try:
            self._client.incr(VERSION_KEY)
        except redis.RedisError as exc:
            logger.warning("Redis bump_version failed: %s", exc)

    def get_json(self, key: str):
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        except (redis.RedisError, json.JSONDecodeError) as exc:
            logger.warning("Redis get_json failed for %s: %s", key, exc)
            return None

    def set_json(self, key: str, value, ttl: int = STRUCTURED_CACHE_TTL) -> None:
        try:
            self._client.set(
                key,
                json.dumps(value, ensure_ascii=False, default=_json_default),
                ex=ttl,
            )
        except redis.RedisError as exc:
            logger.warning("Redis set_json failed for %s: %s", key, exc)


redis_cache = RedisCache()
