"""Redis 签到去重: 当天签到状态 + 10 分钟冷却状态分开存储"""

import logging
import time

from core.redis_client import get_redis_client

from config import (
    CHECKIN_COOLDOWN_SECONDS,
)

logger = logging.getLogger(__name__)

KEY_PREFIX = "checkin"
COOLDOWN_PREFIX = "checkin_cooldown"
CHECKED_OUT_PREFIX = "checkout"


class RedisCheckIn:
    """Redis 签到去重"""

    def __init__(self):
        self._local_date = self._today()
        self._local_checked_in: set[str] = set()
        self._local_checked_out: set[str] = set()
        self._local_cooldowns: dict[str, float] = {}
        self._r = get_redis_client()
        try:
            self._r.ping()
            logger.info(
                "Redis 连接成功: %s:%s",
                self._r.connection_pool.connection_kwargs.get("host"),
                self._r.connection_pool.connection_kwargs.get("port"),
            )
        except Exception as e:
            raise RuntimeError("Redis 不可用") from e

    def _today_key(self, name: str) -> str:
        return f"{KEY_PREFIX}:{self._today()}:{name}"

    def _checkout_key(self, name: str) -> str:
        return f"{CHECKED_OUT_PREFIX}:{self._today()}:{name}"

    def _cooldown_key(self, name: str) -> str:
        return f"{COOLDOWN_PREFIX}:{name}"

    def _today_set_key(self) -> str:
        return f"{KEY_PREFIX}:{self._today()}:set"

    def is_checked_in_today(self, name: str) -> bool:
        self._reset_local_if_new_day()
        if name in self._local_checked_in:
            return True
        if self._r is None:
            return False
        try:
            exists = bool(self._r.exists(self._today_key(name)))
            if exists:
                self._local_checked_in.add(name)
            return exists
        except Exception as exc:
            logger.warning(
                "Redis 今日签到状态读取失败, 使用本地兜底 (%s): %s", name, exc
            )
            return name in self._local_checked_in

    def is_checked_out_today(self, name: str) -> bool:
        self._reset_local_if_new_day()
        if name in self._local_checked_out:
            return True
        if self._r is None:
            return False
        try:
            exists = bool(self._r.exists(self._checkout_key(name)))
            if exists:
                self._local_checked_out.add(name)
            return exists
        except Exception as exc:
            logger.warning(
                "Redis 今日签退状态读取失败, 使用本地兜底 (%s): %s", name, exc
            )
            return name in self._local_checked_out

    def can_checkin(self, name: str, now: float | None = None) -> bool:
        self._reset_local_if_new_day()
        now = time.time() if now is None else now
        if self._local_cooldowns.get(name, 0.0) > now:
            return False
        if self._r is None:
            return True
        try:
            ttl = self._r.ttl(self._cooldown_key(name))
            return ttl <= 0
        except Exception as exc:
            logger.warning("Redis 签到冷却读取失败, 使用本地兜底 (%s): %s", name, exc)
            return self._local_cooldowns.get(name, 0.0) <= now

    def mark_checked_in(self, name: str) -> None:
        self._reset_local_if_new_day()
        self._local_checked_in.add(name)
        self._local_checked_out.discard(name)
        self._local_cooldowns[name] = time.time() + CHECKIN_COOLDOWN_SECONDS
        if self._r is None:
            return
        try:
            self._r.setex(self._today_key(name), self._seconds_until_tomorrow(), "1")
            self._r.setex(self._cooldown_key(name), CHECKIN_COOLDOWN_SECONDS, "1")
            self._r.sadd(self._today_set_key(), name)
            self._r.expire(self._today_set_key(), 86400)
        except Exception as exc:
            logger.warning("Redis 签到状态写入失败, 已保留本地兜底 (%s): %s", name, exc)

    def mark_checked_out(self, name: str) -> None:
        self._reset_local_if_new_day()
        self._local_checked_out.add(name)
        if self._r is None:
            return
        key = self._checkout_key(name)
        try:
            self._r.setex(key, 86400, "1")
        except Exception as exc:
            logger.warning("Redis 签退状态写入失败, 已保留本地兜底 (%s): %s", name, exc)

    def reset_checkin(self, name: str) -> None:
        self._reset_local_if_new_day()
        self._local_checked_in.discard(name)
        self._local_cooldowns.pop(name, None)
        if self._r is None:
            self.mark_checked_out(name)
            return
        try:
            self._r.delete(self._today_key(name))
            self._r.delete(self._cooldown_key(name))
        except Exception as exc:
            logger.warning("Redis 签到状态清理失败, 已保留本地兜底 (%s): %s", name, exc)
        self.mark_checked_out(name)

    def get_today_count(self) -> int:
        self._reset_local_if_new_day()
        if self._r is None:
            return len(self._local_checked_in)
        try:
            return self._r.scard(self._today_set_key())
        except Exception as exc:
            logger.warning("Redis 今日签到人数读取失败, 使用本地兜底: %s", exc)
            return len(self._local_checked_in)

    @staticmethod
    def _today() -> str:
        from datetime import date

        return date.today().isoformat()

    def _reset_local_if_new_day(self) -> None:
        today = self._today()
        if self._local_date == today:
            return
        self._local_date = today
        self._local_checked_in.clear()
        self._local_checked_out.clear()
        self._local_cooldowns.clear()

    @staticmethod
    def _seconds_until_tomorrow() -> int:
        from datetime import datetime, timedelta

        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return max(1, int((tomorrow - now).total_seconds()))
