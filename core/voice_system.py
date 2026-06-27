"""Queue based TTS, audio playback, and Live2D event pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import (
    AUDIO_QUEUE_MAXSIZE,
    AVATAR_SERVER_URL,
    TTS_CACHE_DIR,
    TTS_QUEUE_MAXSIZE,
    TTS_VOICE,
    TTS_VOICE_BY_MODEL,
)
from core.tts_texts import TTS_TEXTS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TTSRequest:
    event_type: str
    text: str
    name: str = ""
    voice: str = TTS_VOICE


@dataclass(frozen=True)
class AudioJob:
    path: str
    event_type: str
    name: str = ""


@dataclass(frozen=True)
class Live2DAction:
    event_type: str
    payload: dict


class TTSAudioCache:
    """Disk backed hash cache with a small in-memory LRU index."""

    def __init__(self, cache_dir: str = TTS_CACHE_DIR, max_items: int = 256):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self._lock = threading.Lock()
        self._lru: OrderedDict[str, str] = OrderedDict()

    def key_for(self, request: TTSRequest, cache_material: str) -> str:
        raw = "|".join(
            [
                "edge-tts",
                request.voice,
                request.event_type,
                request.text,
                cache_material,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def path_for_key(self, key: str, extension: str = ".mp3") -> str:
        return str(self.cache_dir / f"{key}{extension}")

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            path = self._lru.get(key)
            if not path:
                path = self.path_for_key(key)
            if not path:
                return None
            if os.path.exists(path) and os.path.getsize(path) > 0:
                self._lru[key] = path
                self._lru.move_to_end(key)
                return path
            self._lru.pop(key, None)
            return None

    def put(self, key: str, path: str) -> None:
        with self._lock:
            self._lru[key] = path
            self._lru.move_to_end(key)
            while len(self._lru) > self.max_items:
                self._lru.popitem(last=False)


class EdgeTTSClient:
    """Edge TTS backend, kept async by running inside TTSWorkerThread."""

    def build_cache_material(self, request: TTSRequest) -> str:
        return "|".join(["edge-tts", request.voice, request.text])

    def synthesize_to_file(self, request: TTSRequest, path: str) -> None:
        import asyncio

        asyncio.run(self._synthesize(request, path))

    async def _synthesize(self, request: TTSRequest, path: str) -> None:
        import edge_tts

        communicate = edge_tts.Communicate(request.text, request.voice)
        with open(path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])


class TTSWorkerThread(threading.Thread):
    """Consumes TTS requests, uses cache, and emits playable audio jobs."""

    def __init__(
        self,
        tts_queue: queue.Queue,
        audio_queue: queue.Queue,
        cache: TTSAudioCache,
        client,
    ):
        super().__init__(name="TTSWorkerThread", daemon=True)
        self.tts_queue = tts_queue
        self.audio_queue = audio_queue
        self.cache = cache
        self.client = client
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()
        self.tts_queue.put(None)

    def run(self) -> None:
        while not self._stop_event.is_set():
            request = self.tts_queue.get()
            if request is None:
                break
            try:
                cache_material = self.client.build_cache_material(request)
                key = self.cache.key_for(request, cache_material)
                path = self.cache.get(key)
                if not path:
                    path = self.cache.path_for_key(key)
                    tmp_path = f"{path}.tmp.mp3"
                    self.client.synthesize_to_file(request, tmp_path)
                    os.replace(tmp_path, path)
                    self.cache.put(key, path)
                    logger.info("Edge TTS generated: %s -> %s", request.text, path)
                else:
                    logger.debug("TTS cache hit: %s", request.text)
                self.audio_queue.put(AudioJob(path=path, event_type=request.event_type, name=request.name))
            except Exception as exc:
                logger.warning("TTS request skipped (%s): %s", request.event_type, exc)
            finally:
                self.tts_queue.task_done()


class AudioPlayerThread(threading.Thread):
    """Serial audio playback worker. Face recognition never waits on it."""

    def __init__(self, audio_queue: queue.Queue):
        super().__init__(name="AudioPlayerThread", daemon=True)
        self.audio_queue = audio_queue
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()
        self.audio_queue.put(None)

    def run(self) -> None:
        import pygame.mixer

        pygame.mixer.init()
        while not self._stop_event.is_set():
            job = self.audio_queue.get()
            if job is None:
                break
            try:
                pygame.mixer.music.load(job.path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                    time.sleep(0.02)
            except Exception as exc:
                logger.warning("Audio playback failed (%s): %s", job.path, exc)
            finally:
                self.audio_queue.task_done()


class Live2DController(threading.Thread):
    """Asynchronous Live2D HTTP dispatcher."""

    def __init__(self, base_url: str = AVATAR_SERVER_URL):
        super().__init__(name="Live2DController", daemon=True)
        self.base_url = base_url.rstrip("/")
        self.action_queue: queue.Queue[Optional[Live2DAction]] = queue.Queue(maxsize=64)
        self._stop_event = threading.Event()

    def enqueue(self, event_type: str, payload: dict) -> None:
        try:
            self.action_queue.put_nowait(Live2DAction(event_type, payload))
        except queue.Full:
            logger.debug("Live2D action dropped because queue is full: %s", event_type)

    def stop(self) -> None:
        self._stop_event.set()
        self.action_queue.put(None)

    def run(self) -> None:
        while not self._stop_event.is_set():
            action = self.action_queue.get()
            if action is None:
                break
            try:
                import json

                data = json.dumps({"type": action.event_type, **action.payload}, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.base_url}/event",
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=0.5).close()
            except Exception:
                pass
            finally:
                self.action_queue.task_done()


class EmotionDecisionModule:
    """Converts face events into Live2D actions and key-event speech."""

    SPEECH_EVENTS = {"check_in", "check_out", "repeat", "first_time", "returning", "stranger", "idle_long", "crowd"}
    SILENT_ACTIONS = {"attention"}

    def __init__(self, tts_queue: queue.Queue, live2d: Live2DController):
        self.tts_queue = tts_queue
        self.live2d = live2d
        self._last_model_key = ""
        self._last_voice = TTS_VOICE
        self._last_voice_refresh = 0.0

    def on_avatar_event(self, event_type: str, payload: dict) -> None:
        self.live2d.enqueue(event_type, payload)

        if event_type in self.SILENT_ACTIONS:
            return

        speech_type = self._resolve_speech_type(event_type, payload)
        if speech_type not in self.SPEECH_EVENTS:
            return

        name = payload.get("name", "访客")
        text = self._pick_text(speech_type, name)
        if not text:
            return

        try:
            voice = payload.get("voice") or self._resolve_current_voice()
            self.tts_queue.put_nowait(
                TTSRequest(
                    event_type=speech_type,
                    text=text,
                    name=name,
                    voice=voice,
                )
            )
        except queue.Full:
            logger.debug("TTS request dropped because queue is full: %s", speech_type)

    def _resolve_speech_type(self, event_type: str, payload: dict) -> str:
        if event_type == "check_in" and payload.get("is_first"):
            return "first_time"
        if event_type == "check_in" and payload.get("is_returning"):
            return "returning"
        return event_type

    def _pick_text(self, event_type: str, name: str) -> str:
        import random

        candidates = TTS_TEXTS.get(event_type)
        if not candidates:
            return ""
        return random.choice(candidates).format(name)

    def _resolve_current_voice(self) -> str:
        now = time.time()
        if now - self._last_voice_refresh < 1.0:
            return self._last_voice

        self._last_voice_refresh = now
        try:
            with urllib.request.urlopen(f"{AVATAR_SERVER_URL}/avatar-ready", timeout=0.2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            model_key = str(data.get("model") or "")
            if model_key:
                self._last_model_key = model_key
                self._last_voice = TTS_VOICE_BY_MODEL.get(model_key, TTS_VOICE)
        except Exception:
            self._last_voice = TTS_VOICE_BY_MODEL.get(self._last_model_key, TTS_VOICE)
        return self._last_voice


class VoiceSystem:
    """Convenience wrapper that owns all speech related queues and workers."""

    def __init__(self):
        self.tts_queue: queue.Queue[Optional[TTSRequest]] = queue.Queue(maxsize=TTS_QUEUE_MAXSIZE)
        self.audio_queue: queue.Queue[Optional[AudioJob]] = queue.Queue(maxsize=AUDIO_QUEUE_MAXSIZE)
        self.cache = TTSAudioCache()
        self.tts_client = EdgeTTSClient()
        self.live2d = Live2DController()
        self.emotion = EmotionDecisionModule(self.tts_queue, self.live2d)
        self.tts_worker = TTSWorkerThread(self.tts_queue, self.audio_queue, self.cache, self.tts_client)
        self.audio_player = AudioPlayerThread(self.audio_queue)

    def start(self) -> None:
        self.live2d.start()
        self.tts_worker.start()
        self.audio_player.start()
        logger.info("Voice system started: Live2D + TTS worker + audio player")

    def stop(self) -> None:
        self.tts_worker.stop()
        self.audio_player.stop()
        self.live2d.stop()
