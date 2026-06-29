"""Gender helpers for InsightFace demographic attributes."""

from __future__ import annotations

from typing import Any

GENDER_FEMALE = "female"
GENDER_MALE = "male"

_SALUTATIONS = {
    GENDER_FEMALE: "小姐姐",
    GENDER_MALE: "小哥哥",
}

_DISPLAY_NAMES = {
    GENDER_FEMALE: "女性",
    GENDER_MALE: "男性",
}


def normalize_gender(value: Any) -> str | None:
    """Normalize InsightFace gender output to a stable internal value."""
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {GENDER_FEMALE, "f", "woman", "girl", "0"}:
            return GENDER_FEMALE
        if normalized in {GENDER_MALE, "m", "man", "boy", "1"}:
            return GENDER_MALE
        return None

    try:
        code = int(value)
    except (TypeError, ValueError):
        return None

    if code == 0:
        return GENDER_FEMALE
    if code == 1:
        return GENDER_MALE
    return None


def gender_salutation(gender: str | None, fallback: str = "访客") -> str:
    return _SALUTATIONS.get(gender or "", fallback)


def gender_display_name(gender: str | None, fallback: str = "未知") -> str:
    return _DISPLAY_NAMES.get(gender or "", fallback)
