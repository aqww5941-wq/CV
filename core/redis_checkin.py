"""Redis 签到去重: 用 TTL 替代 JSON 文件, 天然支持 10 分钟冷却"""

import logging

import redis

from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    REDIS_DB,
    CHECKIN_COOLDOWN_SECONDS,
)

logger = logging.getLogger(__name__)

KEY_PREFIX = "checkin"
CHECKED_OUT_PREFIX = "checkout"


class RedisCheckIn:
    """Redis 签到去重"""

    def __init__(self):
        self._r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=REDIS_DB,
            decode_responses=True,
        )
        try:
            self._r.ping()
            logger.info("Redis 连接成功: %s:%s", REDIS_HOST, REDIS_PORT)
        except Exception:
            logger.warning("Redis 不可用, 签到去重降级为内存模式")
            self._r = None

    def _today_key(self, name: str) -> str:
        from datetime import date

        today = date.today().isoformat()
        return f"{KEY_PREFIX}:{today}:{name}"

    def _checkout_key(self, name: str) -> str:
        from datetime import date

        today = date.today().isoformat()
        return f"{CHECKED_OUT_PREFIX}:{today}:{name}"

    def _today_set_key(self) -> str:
        from datetime import date

        return f"{KEY_PREFIX}:{date.today().isoformat()}:set"

    def is_checked_in_today(self, name: str) -> bool:
        if self._r is None:
            return False
        return bool(self._r.exists(self._today_key(name)))

    def is_checked_out_today(self, name: str) -> bool:
        if self._r is None:
            return False
        return bool(self._r.exists(self._checkout_key(name)))

    def can_checkin(self, name: str, now: float | None = None) -> bool:
        if self._r is None:
            return True
        ttl = self._r.ttl(self._today_key(name))
        return ttl <= 0

    def mark_checked_in(self, name: str) -> None:
        if self._r is None:
            return
        key = self._today_key(name)
        self._r.setex(key, CHECKIN_COOLDOWN_SECONDS, "1")
        self._r.sadd(self._today_set_key(), name)
        self._r.expire(self._today_set_key(), 86400)

    def mark_checked_out(self, name: str) -> None:
        if self._r is None:
            return
        key = self._checkout_key(name)
        self._r.setex(key, 86400, "1")

    def reset_checkin(self, name: str) -> None:
        if self._r is None:
            return
        self._r.delete(self._today_key(name))
        self.mark_checked_out(name)

    def get_today_count(self) -> int:
        if self._r is None:
            return 0
        return self._r.scard(self._today_set_key())
