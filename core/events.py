"""消息队列事件发布: 签到/签退事件推送到 MQ, 下游系统可订阅"""

import json
import logging
import time
from datetime import datetime

from config import MQ_BACKEND, MQ_TOPIC_PREFIX

logger = logging.getLogger(__name__)


class EventBus:
    """事件总线: 支持 Redis Pub/Sub 和内存回退"""

    def __init__(self):
        self._backend = self._init_backend()

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
            return
        if hasattr(self._backend, "publish"):
            self._backend.publish(topic, json.dumps(message, ensure_ascii=False))
        elif hasattr(self._backend, "send"):
            self._backend.send(topic, message)
        logger.debug("EVENT | %s | %s", topic, payload.get("name", "?"))

    def checkin(self, name: str, row_id: int, similarity: float) -> None:
        self.publish(
            "checkin",
            {
                "name": name,
                "row_id": row_id,
                "similarity": round(similarity, 4),
                "time": time.time(),
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

    def stranger(self, bbox: list[int]) -> None:
        self.publish(
            "stranger_detected",
            {"bbox": bbox, "time": time.time()},
        )
