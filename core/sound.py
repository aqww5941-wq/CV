"""语音播报模块: 打卡成功时播放"欢迎光临"语音。预生成 WAV 实现毫秒级响应。"""

import logging
import os
import subprocess
import sys
import threading

from config import CACHE_DIR

logger = logging.getLogger(__name__)

_WAV_PATH = os.path.join(CACHE_DIR, "welcome.wav")
_GOODBYE_WAV_PATH = os.path.join(CACHE_DIR, "goodbye.wav")


def play_welcome() -> None:
    t = threading.Thread(target=_play_welcome, daemon=True)
    t.start()


def _play_welcome() -> None:
    if os.path.exists(_WAV_PATH):
        try:
            _play_wav()
            return
        except Exception as e:
            logger.debug("WAV 播放失败: %s", e)

    for backend in (_play_espeak, _play_powershell):
        try:
            backend()
            return
        except Exception:
            pass

    logger.warning("无可用语音后端, 跳过语音播报")


def _play_wav() -> None:
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(_WAV_PATH, winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        subprocess.run(
            ["aplay", "-q", _WAV_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )


def _play_espeak() -> None:
    subprocess.run(
        ["espeak", "-v", "zh", "欢迎光临"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def _play_powershell() -> None:
    subprocess.run(
        [
            "powershell",
            "-Command",
            '(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("欢迎光临")',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def play_goodbye() -> None:
    t = threading.Thread(target=_play_goodbye, daemon=True)
    t.start()


def _play_goodbye() -> None:
    if os.path.exists(_GOODBYE_WAV_PATH):
        try:
            _play_goodbye_wav()
            return
        except Exception as e:
            logger.debug("WAV 播放失败: %s", e)

    for backend in (_play_goodbye_espeak, _play_goodbye_powershell):
        try:
            backend()
            return
        except Exception:
            pass

    logger.warning("无可用语音后端, 跳过签退语音")


def _play_goodbye_wav() -> None:
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(
            _GOODBYE_WAV_PATH, winsound.SND_FILENAME | winsound.SND_ASYNC
        )
    else:
        subprocess.run(
            ["aplay", "-q", _GOODBYE_WAV_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )


def _play_goodbye_espeak() -> None:
    subprocess.run(
        ["espeak", "-v", "zh", "明天见"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def _play_goodbye_powershell() -> None:
    subprocess.run(
        [
            "powershell",
            "-Command",
            '(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("明天见")',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
