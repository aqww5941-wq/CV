"""每日签到去重: 同一个人同一天只打卡一次, 签退后当天不再打卡, 签到后10分钟内不再签"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date

from config import CACHE_DIR, CHECKIN_COOLDOWN_SECONDS

logger = logging.getLogger(__name__)

CHECKIN_FILE = os.path.join(CACHE_DIR, "checkins.json")


class CheckInTracker:
    """每日签到去重记录 + 10分钟签到冷却"""

    def __init__(self):
        self._records: dict[str, list[str]] = {}
        self._checked_out: set[str] = set()
        self._last_checkin_time: dict[str, float] = {}
        self._load()

    def _load(self):
        if os.path.exists(CHECKIN_FILE):
            with open(CHECKIN_FILE, "r") as f:
                data = json.load(f)
                if "records" in data:
                    self._records = data["records"]
                    self._checked_out = set(data.get("checked_out", []))
                else:
                    self._records = data
                    self._checked_out = set()

    def _save(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CHECKIN_FILE, "w") as f:
            json.dump(
                {
                    "records": self._records,
                    "checked_out": list(self._checked_out),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def is_checked_in_today(self, name: str) -> bool:
        today = date.today().isoformat()
        return name in self._records.get(today, [])

    def is_checked_out_today(self, name: str) -> bool:
        return name in self._checked_out

    def mark_checked_in(self, name: str):
        today = date.today().isoformat()
        if today not in self._records:
            self._records[today] = []
        if name not in self._records[today]:
            self._records[today].append(name)
            self._save()
        self._last_checkin_time[name] = time.time()

    def can_checkin(self, name: str, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        last = self._last_checkin_time.get(name, 0)
        return (now - last) >= CHECKIN_COOLDOWN_SECONDS

    def get_today_count(self) -> int:
        today = date.today().isoformat()
        return len(self._records.get(today, []))

    def reset_checkin(self, name: str):
        self._checked_out.add(name)
        today = date.today().isoformat()
        if today in self._records:
            self._checked_out = {
                n for n in self._checked_out if n in self._records.get(today, [])
            }
        self._save()

    def cleanup(self):
        today = date.today()
        expired = [
            d for d in self._records if (date.fromisoformat(d) - today).days < -7
        ]
        for d in expired:
            del self._records[d]
        self._checked_out = set()
        self._save()
