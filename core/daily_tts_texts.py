"""Daily generated TTS texts with built-in fallback."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
import threading

from config import DAILY_TTS_TEXTS_FILE

logger = logging.getLogger(__name__)
_TEXTS_LOCK = threading.RLock()
_TEXT_POOLS: dict[tuple[str, bool | None], list[str]] = {}
_LAST_TEXTS: dict[tuple[str, bool | None], str] = {}

EVENT_TYPES = {
    "check_in",
    "check_out",
    "stranger",
    "returning_stranger",
    "repeat",
    "first_time",
    "returning",
    "idle_long",
    "crowd",
}


def load_daily_texts() -> dict[str, list[str]]:
    path = Path(DAILY_TTS_TEXTS_FILE)
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logger.warning("每日语录读取失败，使用内置语录: %s", exc)
        return {}

    if payload.get("date") != date.today().isoformat():
        return {}

    texts = payload.get("texts")
    if not isinstance(texts, dict):
        return {}

    result: dict[str, list[str]] = {}
    for event_type in EVENT_TYPES:
        values = texts.get(event_type)
        if not isinstance(values, list):
            continue
        cleaned = [
            _normalize_template(str(value).strip())
            for value in values
            if str(value).strip()
        ]
        if cleaned:
            result[event_type] = cleaned
    return result


def merge_daily_texts(default_texts: dict[str, list[str]]) -> dict[str, list[str]]:
    daily_texts = load_daily_texts()
    if not daily_texts:
        return default_texts

    merged = {key: list(values) for key, values in default_texts.items()}
    for event_type, values in daily_texts.items():
        merged[event_type] = values
    logger.info("已加载今日数字人语录: %s", DAILY_TTS_TEXTS_FILE)
    return merged


def refresh_texts(default_texts: dict[str, list[str]], target: dict[str, list[str]]) -> None:
    merged = merge_daily_texts(default_texts)
    with _TEXTS_LOCK:
        target.clear()
        target.update(merged)
        _TEXT_POOLS.clear()
        _LAST_TEXTS.clear()


def choose_text(
    texts: dict[str, list[str]],
    event_type: str,
    require_placeholder: bool | None = None,
) -> str:
    import random

    with _TEXTS_LOCK:
        candidates = _filter_candidates(texts.get(event_type) or [], require_placeholder)
        if not candidates:
            return ""

        pool_key = (event_type, require_placeholder)
        pool = _TEXT_POOLS.get(pool_key)
        if not pool or any(item not in candidates for item in pool):
            pool = _reshuffle(candidates, _LAST_TEXTS.get(pool_key), random)
            _TEXT_POOLS[pool_key] = pool

        text = pool.pop()
        _LAST_TEXTS[pool_key] = text
        return text


def _filter_candidates(values: list[str], require_placeholder: bool | None) -> list[str]:
    candidates = list(dict.fromkeys(values))
    if require_placeholder is None:
        return candidates
    return [text for text in candidates if ("{}" in text) == require_placeholder]


def _reshuffle(candidates: list[str], last_text: str | None, random_module) -> list[str]:
    pool = list(candidates)
    random_module.shuffle(pool)
    if len(pool) > 1 and pool[-1] == last_text:
        pool.insert(0, pool.pop())
    return pool


def _normalize_template(value: str) -> str:
    return value.replace("{name}", "{}")
