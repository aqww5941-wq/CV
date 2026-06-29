"""Redis 连接池工厂: 统一管理所有 Redis 连接, 避免单连接超时"""

import logging

import redis
from redis import ConnectionPool

from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    REDIS_DB,
    REDIS_POOL_SIZE,
    REDIS_POOL_MAX_OVERFLOW,
)

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    _pool = ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        db=REDIS_DB,
        decode_responses=True,
        max_connections=REDIS_POOL_SIZE,
        socket_connect_timeout=2,
        socket_timeout=2,
        socket_keepalive=True,
        health_check_interval=30,
        retry_on_timeout=True,
    )
    return _pool


def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=get_redis_pool())


def ping_redis() -> bool:
    try:
        client = get_redis_client()
        client.ping()
        return True
    except Exception as exc:
        logger.warning("Redis 连接失败: %s", exc)
        return False
