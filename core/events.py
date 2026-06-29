"""消息队列事件发布: 签到/签退事件推送到 Redis 和数字人前端"""

import json
import logging
import time
from datetime import datetime

from config import MQ_TOPIC_PREFIX

logger = logging.getLogger(__name__)


class EventBus:
    """事件总线: 支持 Redis Pub/Sub + 数字人前端事件."""

    def __init__(self, emotion_module=None):
        self._backend = self._init_backend()
        self._emotion_module = emotion_module
        self._last_avatar_event: dict | None = None
        self._last_avatar_time: float = 0.0

    def _init_backend(self):
        try:
            from core.redis_client import get_redis_client

            r = get_redis_client()
            r.ping()
            logger.info("事件总线就绪: Redis Pub/Sub")
            return r
        except Exception as e:
            logger.warning("Redis 不可用, 事件总线降级为日志模式: %s", e)
            return None

    def publish(self, event_type: str, payload: dict) -> None:
        topic = f"{MQ_TOPIC_PREFIX}.{event_type}"
        message = {
            "event": event_type,
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "payload": payload,
        }
        if isinstance(self._backend, type(None)):
            logger.info(
                "EVENT | %s | %s", topic, json.dumps(payload, ensure_ascii=False)
            )
        elif hasattr(self._backend, "publish"):
            try:
                self._backend.publish(topic, json.dumps(message, ensure_ascii=False))
            except Exception as exc:
                logger.warning("Redis 事件发布失败, 降级为日志模式: %s", exc)
                self._backend = None
                logger.info(
                    "EVENT | %s | %s", topic, json.dumps(payload, ensure_ascii=False)
                )
        logger.debug("EVENT | %s | %s", topic, payload.get("name", "?"))

    def _avatar_event(self, event_type: str, payload: dict) -> None:
        msg = {"type": event_type, **payload}
        self._last_avatar_event = msg
        self._last_avatar_time = time.time()
        if self._emotion_module is not None:
            self._emotion_module.on_avatar_event(event_type, payload)

    def checkin(
        self,
        name: str,
        row_id: int,
        similarity: float,
        is_first: bool = False,
        is_returning: bool = False,
    ) -> None:
        self.publish(
            "checkin",
            {
                "name": name,
                "row_id": row_id,
                "similarity": round(similarity, 4),
                "time": time.time(),
            },
        )
        self._avatar_event(
            "check_in",
            {
                "name": name,
                "is_first": is_first,
                "is_returning": is_returning,
            },
        )

    def checkout(self, name: str, row_id: int, duration_minutes: int) -> None:
        self.publish(
            "checkout",
            {
                "name": name,
                "row_id": row_id,
                "duration_minutes": duration_minutes,
                "time": time.time(),
            },
        )
        self._avatar_event("check_out", {"name": name})

    def stranger(
        self,
        visitor_label: str | None = None,
        is_returning: bool = False,
        gender: str | None = None,
        salutation: str | None = None,
    ) -> None:
        payload = {
            "time": time.time(),
            "visitor_label": visitor_label or "未知访客",
            "is_returning": is_returning,
            "gender": gender,
            "salutation": salutation,
        }
        self.publish("stranger_detected", payload)
        self._avatar_event("stranger", payload)

    def repeat_checkin(self, name: str) -> None:
        self.publish("repeat_checkin", {"name": name, "time": time.time()})
        self._avatar_event("repeat", {"name": name})

    def attention(self) -> None:
        now = time.time()
        if (
            self._last_avatar_event
            and self._last_avatar_event.get("type") == "attention"
        ):
            if now - self._last_avatar_time < 5.0:
                return
        self._avatar_event("attention", {})

    def idle_long(self) -> None:
        self._avatar_event("idle_long", {})

    def crowd(self, count: int) -> None:
        now = time.time()
        if self._last_avatar_event and self._last_avatar_event.get("type") == "crowd":
            if now - self._last_avatar_time < 30.0:
                return
        self._avatar_event("crowd", {"count": count})
