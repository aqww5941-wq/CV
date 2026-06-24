"""语音播报模块: Edge TTS 预生成 WAV → 毫秒级播放。降级: PowerShell → ESpeak。"""

import asyncio
import logging
import os
import subprocess
import threading

from config import CACHE_DIR

logger = logging.getLogger(__name__)

_WELCOME_WAV = os.path.join(CACHE_DIR, "welcome.mp3")
_GOODBYE_WAV = os.path.join(CACHE_DIR, "goodbye.mp3")

VOICE = "zh-CN-XiaoxiaoNeural"
WELCOME_TEXT = "欢迎光临"
GOODBYE_TEXT = "明天见"


def generate_edge_wavs() -> None:
    """启动时调用: 用 Edge TTS 预生成语音, 缓存命中跳过"""
    _generate_cached(WELCOME_TEXT, _WELCOME_WAV)
    _generate_cached(GOODBYE_TEXT, _GOODBYE_WAV)


def _generate_cached(text: str, path: str) -> None:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        logger.debug("TTS 缓存命中: %s", path)
        return
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


def play_welcome() -> None:
    t = threading.Thread(target=_play_welcome, daemon=True)
    t.start()


def _play_welcome() -> None:
    if os.path.exists(_WELCOME_WAV) and os.path.getsize(_WELCOME_WAV) > 0:
        try:
            _play_wav(_WELCOME_WAV)
            return
        except Exception as e:
            logger.debug("WAV 播放失败: %s", e)

    for backend in (_play_text_espeak, _play_text_powershell):
        try:
            backend(WELCOME_TEXT)
            return
        except Exception:
            pass

    logger.warning("无可用语音后端, 跳过语音播报")


def play_goodbye() -> None:
    t = threading.Thread(target=_play_goodbye, daemon=True)
    t.start()


def _play_goodbye() -> None:
    if os.path.exists(_GOODBYE_WAV) and os.path.getsize(_GOODBYE_WAV) > 0:
        try:
            _play_wav(_GOODBYE_WAV)
            return
        except Exception as e:
            logger.debug("WAV 播放失败: %s", e)

    for backend in (_play_text_espeak, _play_text_powershell):
        try:
            backend(GOODBYE_TEXT)
            return
        except Exception:
            pass

    logger.warning("无可用语音后端, 跳过签退语音")


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
