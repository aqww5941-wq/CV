"""语音播报模块: Edge TTS 预生成 mp3 → 毫秒级播放。降级: PowerShell → ESpeak。"""

import asyncio
import logging
import os
import random
import subprocess
import threading

from config import CACHE_DIR
from core.tts_texts import TTS_TEXTS, VOICE

logger = logging.getLogger(__name__)

_CACHE = {}


def _cache_path(event_type: str) -> str:
    return os.path.join(CACHE_DIR, f"tts_{event_type}.mp3")


def generate_edge_wavs() -> None:
    """启动时调用: 预生成所有 TTS 缓存 (随机选一个变体)"""
    for event_type, candidates in TTS_TEXTS.items():
        path = _cache_path(event_type)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            logger.debug("TTS 缓存命中: %s", event_type)
            continue
        template = random.choice(candidates)
        text = template.format("")
        _generate_wav(text, path)


def _generate_wav(text: str, path: str) -> None:
    try:
        asyncio.run(_generate_edge_tts(text, path))
    except Exception as e:
        logger.debug("Edge TTS 生成失败 (%s): %s", text, e)


async def _generate_edge_tts(text: str, path: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE)
    with open(path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
    logger.info("Edge TTS 生成: %s → %s", text, path)


def play_tts(event_type: str, name: str = "") -> None:
    """播放指定事件类型的语音, 异步不阻塞"""
    t = threading.Thread(target=_play_tts, args=(event_type, name), daemon=True)
    t.start()


def _play_tts(event_type: str, name: str) -> None:
    path = _cache_path(event_type)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            _play_wav(path)
            return
        except Exception as e:
            logger.debug("mp3 播放失败: %s", e)

    candidates = TTS_TEXTS.get(event_type, ["{}"])
    template = random.choice(candidates)
    text = template.format(name)

    for backend in (_play_text_espeak, _play_text_powershell):
        try:
            backend(text)
            return
        except Exception:
            pass

    logger.warning("无可用语音后端, 跳过语音播报")


def play_welcome() -> None:
    play_tts("check_in")


def play_goodbye() -> None:
    play_tts("check_out")


def _play_wav(path: str) -> None:
    import pygame.mixer

    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()


def _play_text_espeak(text: str) -> None:
    subprocess.run(
        ["espeak", "-v", "zh", text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def _play_text_powershell(text: str) -> None:
    subprocess.run(
        [
            "powershell",
            "-Command",
            f'(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{text}")',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
