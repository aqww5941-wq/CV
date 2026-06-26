"""消息队列事件发布: 签到/签退事件推送到 MQ 和数字人前端"""

import json
import logging
import time
import urllib.request
from datetime import datetime

from config import MQ_BACKEND, MQ_TOPIC_PREFIX, AVATAR_SERVER_URL

logger = logging.getLogger(__name__)


class EventBus:
    """事件总线: 支持 Redis Pub/Sub + HTTP 推送到数字人前端"""

    def __init__(self):
        self._backend = self._init_backend()
        self._avatar_url = f"{AVATAR_SERVER_URL}/event"
        self._last_avatar_event: dict | None = None
        self._last_avatar_time: float = 0.0

    def _init_backend(self):
        if MQ_BACKEND == "redis":
            try:
                import redis as rd

                from config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB

                r = rd.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    password=REDIS_PASSWORD or None,
                    db=REDIS_DB,
                    decode_responses=True,
                )
                r.ping()
                logger.info("事件总线就绪: Redis Pub/Sub")
                return r
            except Exception as e:
                logger.warning("Redis 不可用, 事件总线降级为日志模式: %s", e)
                return None
        elif MQ_BACKEND == "kafka":
            try:
                from kafka import KafkaProducer

                producer = KafkaProducer(
                    bootstrap_servers="localhost:9092",
                    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(
                        "utf-8"
                    ),
                )
                logger.info("事件总线就绪: Kafka")
                return producer
            except Exception as e:
                logger.warning("Kafka 不可用, 事件总线降级为日志模式: %s", e)
                return None
        else:
            logger.warning("未知 MQ 后端 %s, 事件总线降级为日志模式", MQ_BACKEND)
            return None

    def _send_to_avatar(self, event: dict) -> None:
        try:
            data = json.dumps(event, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                self._avatar_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass

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
            self._backend.publish(topic, json.dumps(message, ensure_ascii=False))
        elif hasattr(self._backend, "send"):
            self._backend.send(topic, message)
        logger.debug("EVENT | %s | %s", topic, payload.get("name", "?"))

    def _avatar_event(self, event_type: str, payload: dict) -> None:
        msg = {"type": event_type, **payload}
        self._last_avatar_event = msg
        self._last_avatar_time = time.time()
        self._send_to_avatar(msg)

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

    def stranger(self) -> None:
        self.publish("stranger_detected", {"time": time.time()})
        self._avatar_event("stranger", {})

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
        self._avatar_event("crowd", {"count": count})
