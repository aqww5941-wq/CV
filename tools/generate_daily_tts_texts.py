"""Generate daily avatar TTS text variants via an OpenAI-compatible chat API."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    DAILY_QUOTES_API_BASE,
    DAILY_QUOTES_API_KEY,
    DAILY_QUOTES_MODEL,
    DAILY_QUOTES_TEMPERATURE,
    DAILY_QUOTES_TIMEOUT_SECONDS,
    DAILY_TTS_TEXTS_FILE,
)
from core.daily_tts_texts import EVENT_TYPES

TEXT_COUNTS = {
    "check_in": 8,
    "repeat": 10,
    "check_out": 6,
    "stranger": 5,
    "returning_stranger": 4,
    "first_time": 4,
    "returning": 4,
    "idle_long": 4,
    "crowd": 4,
}

NAME_PLACEHOLDER_COUNTS = {
    "check_in": {"with_name": 8, "without_name": 0},
    "repeat": {"with_name": 3, "without_name": 7},
    "check_out": {"with_name": 6, "without_name": 0},
    "stranger": {"with_name": 3, "without_name": 2},
    "returning_stranger": {"with_name": 2, "without_name": 2},
    "first_time": {"with_name": 3, "without_name": 1},
    "returning": {"with_name": 2, "without_name": 2},
    "idle_long": {"with_name": 0, "without_name": 4},
    "crowd": {"with_name": 0, "without_name": 4},
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
SOLAR_FESTIVALS = {
    "01-01": "元旦",
    "02-14": "情人节",
    "03-08": "妇女节",
    "03-12": "植树节",
    "05-01": "劳动节",
    "06-01": "儿童节",
    "09-10": "教师节",
    "10-01": "国庆节",
    "12-25": "圣诞节",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily avatar TTS texts.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", default=DAILY_TTS_TEXTS_FILE)
    parser.add_argument("--allow-fallback", action="store_true")
    args = parser.parse_args()

    output_path = generate_daily_texts(
        target_date=date.fromisoformat(args.date),
        output=args.output,
        allow_fallback=args.allow_fallback,
    )
    print(f"每日语录已生成: {output_path}")
    return 0


def generate_daily_texts(
    target_date: date | None = None,
    output: str | None = None,
    allow_fallback: bool = False,
) -> Path:
    target_date = target_date or date.today()
    context = _build_date_context(target_date)
    source = "model"
    try:
        texts = _generate_with_model(context)
    except Exception as exc:
        if not allow_fallback:
            raise
        print(f"模型生成失败，使用本地兜底语录: {exc}", file=sys.stderr)
        texts = _fallback_texts(context)
        source = "local-fallback"

    payload = {
        "date": target_date.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "model": DAILY_QUOTES_MODEL if source == "model" else "local-fallback",
        "context": context,
        "texts": _validate_texts(texts),
    }
    output_path = Path(output or DAILY_TTS_TEXTS_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)
    return output_path


def _build_date_context(target_date: date) -> dict:
    weekday = target_date.weekday()
    hints = []
    if weekday == 0:
        hints.append("周一，可以鼓励大家开启新一周")
    elif weekday == 4:
        hints.append("周五，可以提到这周最后一个工作日、稳稳收尾")
    elif weekday >= 5:
        hints.append("周末，语气可以更轻松，适合值班或来访场景")

    today_festival = SOLAR_FESTIVALS.get(target_date.strftime("%m-%d"))
    if today_festival:
        hints.append(f"今天是{today_festival}")

    upcoming = _upcoming_solar_festivals(target_date)
    if upcoming:
        hints.extend(upcoming)

    return {
        "date": target_date.isoformat(),
        "weekday": WEEKDAY_NAMES[weekday],
        "hints": hints,
    }


def _upcoming_solar_festivals(target_date: date) -> list[str]:
    hints = []
    for offset in range(1, 8):
        day = target_date + timedelta(days=offset)
        festival = SOLAR_FESTIVALS.get(day.strftime("%m-%d"))
        if festival:
            hints.append(f"{offset}天后是{festival}")
    return hints


def _generate_with_model(context: dict) -> dict[str, list[str]]:
    if not DAILY_QUOTES_API_KEY:
        raise RuntimeError("DAILY_QUOTES_API_KEY is empty")

    prompt = _build_prompt(context)
    payload = {
        "model": DAILY_QUOTES_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是公司前台数字人的中文话术编辑。"
                    "只输出合法 JSON，不要输出解释。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": DAILY_QUOTES_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{DAILY_QUOTES_API_BASE}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DAILY_QUOTES_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DAILY_QUOTES_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(_extract_json(content))
    return parsed.get("texts", parsed)


def _build_prompt(context: dict) -> str:
    counts = json.dumps(TEXT_COUNTS, ensure_ascii=False)
    name_counts = json.dumps(NAME_PLACEHOLDER_COUNTS, ensure_ascii=False)
    hints = "；".join(context["hints"]) if context["hints"] else "普通工作日"
    return f"""
请为公司前台数字人生成当天语音话术。

日期: {context["date"]}
星期: {context["weekday"]}
当天提示: {hints}

要求:
1. 输出 JSON，顶层字段为 texts。
2. texts 下必须包含这些分类及数量: {counts}
3. 每个分类里带姓名和不带姓名的数量必须符合: {name_counts}
4. 带姓名的句子只使用 {{name}} 作为姓名占位；不带姓名的句子绝对不要出现 {{name}}。
5. 需要温暖、自然、有一点轻松感；可以关心、调侃、幽默、问候，但不要油腻。
6. 每句话尽量 8 到 28 个中文字符，适合 TTS 播放，避免长句被截断。
7. check_in 和 check_out 必须每一句都带 {{name}}，不要生成任何不带姓名的签到/签退句。
8. repeat 必须同时包含带 {{name}} 和不带 {{name}} 的句子，用于运行时随机穿插姓名。
9. stranger 可使用 {{name}} 表示“小哥哥/小姐姐”等访客称呼；idle_long/crowd 必须全部不带姓名。
10. crowd 是数字人发现很多人同时看着自己时的害羞、惊喜、开心反应，要像“这么多人看着我，我好害羞呀”这种可爱自我表达。
11. crowd 禁止写成通知、广播、安保或办事引导口吻，不要出现排队、办理手续、电梯口、拥挤、安全、通行、配合、秩序等词。
12. 不要涉及政治、宗教、医疗建议、投资建议，不要说“我是 AI”。
""".strip()


def _validate_texts(texts: dict) -> dict[str, list[str]]:
    if not isinstance(texts, dict):
        raise ValueError("model output must be a JSON object")

    result: dict[str, list[str]] = {}
    fallback = _fallback_texts({"hints": []})
    for event_type in sorted(EVENT_TYPES):
        values = texts.get(event_type) or []
        if not isinstance(values, list):
            values = []
        cleaned = []
        for value in values:
            text = _clean_text(str(value))
            if text:
                cleaned.append(text)
        cleaned = _dedupe(cleaned)
        cleaned = _balance_placeholders(event_type, cleaned, fallback[event_type])
        result[event_type] = cleaned[: TEXT_COUNTS.get(event_type, 4)]
    return result


def _clean_text(value: str) -> str:
    value = value.strip().replace("{name}", "{}")
    value = re.sub(r"\s+", "", value)
    if not value:
        return ""
    if any(bad in value for bad in ["政治", "宗教", "投资建议", "医疗建议"]):
        return ""
    return value


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _balance_placeholders(
    event_type: str,
    values: list[str],
    fallback_values: list[str],
) -> list[str]:
    quota = NAME_PLACEHOLDER_COUNTS.get(event_type)
    if not quota:
        return values

    with_name = [text for text in values if "{}" in text]
    without_name = [text for text in values if "{}" not in text]
    fallback_with_name = [text for text in fallback_values if "{}" in text]
    fallback_without_name = [text for text in fallback_values if "{}" not in text]

    with_target = quota["with_name"]
    without_target = quota["without_name"]
    with_name = _fill_to_count(with_name, fallback_with_name, with_target)
    without_name = _fill_to_count(without_name, fallback_without_name, without_target)

    balanced = with_name[:with_target] + without_name[:without_target]
    random.shuffle(balanced)
    return balanced


def _fill_to_count(values: list[str], fallback_values: list[str], target_count: int) -> list[str]:
    result = _dedupe(values)
    for text in fallback_values:
        if len(result) >= target_count:
            break
        if text not in result:
            result.append(text)
    return result


def _extract_json(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return content


def _fallback_texts(context: dict) -> dict[str, list[str]]:
    hints = context.get("hints") or []
    week_hint = "新一周开始啦，" if any("周一" in hint for hint in hints) else ""
    friday_hint = "这周快收尾啦，" if any("周五" in hint for hint in hints) else ""
    salt = random.randint(1, 9999)
    return {
        "check_in": [
            f"{{}}，{week_hint}今天也稳稳开工。",
            f"{{}}，{friday_hint}保持好心情呀。",
            "{}，早上好，今天也一起加油。",
            "{}，签到成功，元气已到账。",
            "{}，打卡完成，今天顺顺利利。",
            "{}，早呀，今天继续闪亮上班。",
            f"{{}}，{week_hint}早上好，今天也稳稳来。",
            f"{{}}，{friday_hint}签到成功，开心开工。",
        ],
        "repeat": [
            "{}，又见面啦，记得喝口水。",
            "{}，你今天状态持续在线。",
            "{}，别太累，休息也要认真。",
            f"{{}}，今日鼓励编号{salt}送达。",
            "又见面啦，记得喝口水。",
            "状态不错，继续保持节奏。",
            "今天也辛苦啦，别忘了休息。",
            "我还在这儿，继续认真待命。",
            "路过也算打个招呼啦。",
            f"今日鼓励编号{salt}送达。",
        ],
        "check_out": [
            "{}，辛苦啦，今天圆满收工。",
            "{}，签退完成，路上注意安全。",
            "{}，今天表现不错，早点休息。",
            "{}，下班快乐，明天见。",
            "{}，签退完成，路上注意安全。",
            "{}，今天辛苦啦，回去好好放松。",
        ],
        "stranger": [
            "{}你好，欢迎来访，请稍等。",
            "{}，欢迎光临，请先登记。",
            "{}，工作人员会协助您。",
            "您好，欢迎来访，请稍等。",
            "新朋友你好，请到前台登记。",
            "欢迎光临，工作人员会协助您。",
            "您好，请稍等工作人员确认。",
            "欢迎来访，请先完成登记。",
        ],
        "returning_stranger": [
            "{}，又见面啦，欢迎回来。",
            "{}，我记得你来过，请稍等。",
            "又见面啦，欢迎回来。",
            "欢迎回来，请稍等一下。",
        ],
        "first_time": [
            "{}，初次见面，很高兴认识你。",
            "{}，欢迎加入，今天开始认识啦。",
            "{}，第一次打卡成功，欢迎你。",
            "初次见面，今天开始认识啦。",
        ],
        "returning": [
            "{}，欢迎回来，今天也顺顺利利。",
            "{}，好久不见，状态保持不错呀。",
            "欢迎回来，今天也顺顺利利。",
            "好久不见，今天状态不错呀。",
        ],
        "idle_long": [
            "现在有点安静，我继续待命。",
            "前台暂时安静，随时准备接待。",
            "大厅很安静，我在这里守着。",
            "没人经过的时候，也要精神在线。",
        ],
        "crowd": [
            "这么多人看着我，我有点害羞呀。",
            "哇，大家一起出现，我脸都要红啦。",
            "一下子被大家围观，我要认真营业啦。",
            "今天好热闹呀，我都有点小紧张。",
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
