"""Realtime voice dialog service backed by Volcengine Doubao speech API."""

from __future__ import annotations

import asyncio
import gzip
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from config import (
    AVATAR_SERVER_URL,
    REALTIME_DIALOG_ACCESS_KEY,
    REALTIME_DIALOG_APP_ID,
    REALTIME_DIALOG_BASE_URL,
    REALTIME_DIALOG_BOT_NAME,
    REALTIME_DIALOG_CITY,
    REALTIME_DIALOG_INPUT_CHUNK,
    REALTIME_DIALOG_INPUT_SAMPLE_RATE,
    REALTIME_DIALOG_OUTPUT_CHUNK,
    REALTIME_DIALOG_OUTPUT_FORMAT,
    REALTIME_DIALOG_OUTPUT_SAMPLE_RATE,
    REALTIME_DIALOG_RELEASE_GRACE_SECONDS,
    REALTIME_DIALOG_RECV_TIMEOUT,
    REALTIME_DIALOG_RESOURCE_ID,
    REALTIME_DIALOG_SAY_HELLO,
    REALTIME_DIALOG_SPEAKER,
    REALTIME_DIALOG_SPEAKING_STYLE,
    REALTIME_DIALOG_SYSTEM_ROLE,
)
from core import realtime_dialog_protocol as protocol
from core.voice_system import Live2DController, VoiceSystem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RealtimeDialogSettings:
    app_id: str = REALTIME_DIALOG_APP_ID
    access_key: str = REALTIME_DIALOG_ACCESS_KEY
    base_url: str = REALTIME_DIALOG_BASE_URL
    resource_id: str = REALTIME_DIALOG_RESOURCE_ID
    speaker: str = REALTIME_DIALOG_SPEAKER
    output_format: str = REALTIME_DIALOG_OUTPUT_FORMAT
    bot_name: str = REALTIME_DIALOG_BOT_NAME
    system_role: str = REALTIME_DIALOG_SYSTEM_ROLE
    speaking_style: str = REALTIME_DIALOG_SPEAKING_STYLE
    city: str = REALTIME_DIALOG_CITY
    recv_timeout: int = REALTIME_DIALOG_RECV_TIMEOUT
    say_hello: bool = REALTIME_DIALOG_SAY_HELLO
    release_grace_seconds: float = REALTIME_DIALOG_RELEASE_GRACE_SECONDS
    input_sample_rate: int = REALTIME_DIALOG_INPUT_SAMPLE_RATE
    input_chunk: int = REALTIME_DIALOG_INPUT_CHUNK
    output_sample_rate: int = REALTIME_DIALOG_OUTPUT_SAMPLE_RATE
    output_chunk: int = REALTIME_DIALOG_OUTPUT_CHUNK

    @property
    def ready(self) -> bool:
        return bool(self.app_id and self.access_key)


class RealtimeDialogClient:
    def __init__(self, settings: RealtimeDialogSettings, session_id: str):
        self.settings = settings
        self.session_id = session_id
        self.ws = None
        self.logid = ""

    async def connect(self) -> None:
        import websockets

        headers = {
            "X-Api-App-ID": self.settings.app_id,
            "X-Api-Access-Key": self.settings.access_key,
            "X-Api-Resource-Id": self.settings.resource_id,
            "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        try:
            self.ws = await websockets.connect(
                self.settings.base_url,
                extra_headers=headers,
                ping_interval=None,
            )
        except TypeError:
            self.ws = await websockets.connect(
                self.settings.base_url,
                additional_headers=headers,
                ping_interval=None,
            )
        response_headers = getattr(self.ws, "response_headers", None)
        if response_headers is None and getattr(self.ws, "response", None) is not None:
            response_headers = getattr(self.ws.response, "headers", None)
        self.logid = response_headers.get("X-Tt-Logid", "") if response_headers else ""
        await self._send_full_event(1, {})
        logger.info("实时语音连接已建立 logid=%s", self.logid)
        await self._send_full_event(100, self._start_session_payload(), with_session=True)
        logger.info("实时语音会话已启动 session=%s", self.session_id)

    def _start_session_payload(self) -> dict[str, Any]:
        return {
            "asr": {
                "extra": {
                    "end_smooth_window_ms": 1500,
                },
            },
            "tts": {
                "speaker": self.settings.speaker,
                "audio_config": {
                    "channel": 1,
                    "format": self.settings.output_format,
                    "sample_rate": self.settings.output_sample_rate,
                },
            },
            "dialog": {
                "bot_name": self.settings.bot_name,
                "system_role": self.settings.system_role,
                "speaking_style": self.settings.speaking_style,
                "location": {"city": self.settings.city},
                "extra": {
                    "strict_audit": False,
                    "audit_response": "这个问题我暂时不能回答，我们换个轻松的话题吧。",
                    "recv_timeout": self.settings.recv_timeout,
                    "input_mod": "audio",
                },
            },
        }

    async def say_hello(self) -> None:
        await self._send_full_event(
            300,
            {"content": "你好呀，我在这里，可以直接和我说话。"},
            with_session=True,
        )

    async def send_audio(self, audio: bytes) -> None:
        request = protocol.generate_header(
            message_type=protocol.CLIENT_AUDIO_ONLY_REQUEST,
            serial_method=protocol.NO_SERIALIZATION,
        )
        request.extend(int(200).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        payload = gzip.compress(audio)
        request.extend(len(payload).to_bytes(4, "big"))
        request.extend(payload)
        await self.ws.send(request)

    async def receive(self) -> dict[str, Any]:
        return protocol.parse_response(await self.ws.recv())

    async def finish_session(self) -> None:
        await self._send_full_event(102, {}, with_session=True)

    async def finish_connection(self) -> None:
        await self._send_full_event(2, {})

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()

    async def _send_full_event(
        self,
        event: int,
        payload: dict[str, Any],
        with_session: bool = False,
    ) -> None:
        request = protocol.generate_header()
        request.extend(int(event).to_bytes(4, "big"))
        if with_session:
            request.extend(len(self.session_id).to_bytes(4, "big"))
            request.extend(self.session_id.encode("utf-8"))
        payload_bytes = protocol.encode_json_payload(payload)
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        if event in {1, 100, 2}:
            response = protocol.parse_response(await self.ws.recv())
            logger.debug("实时语音事件 %s 响应: %s", event, response)


class AudioDevice:
    def __init__(self, settings: RealtimeDialogSettings):
        import pyaudio

        self.settings = settings
        self.pyaudio_module = pyaudio
        self.pyaudio = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None

    def open_input(self):
        self.input_stream = self.pyaudio.open(
            format=self.pyaudio_module.paInt16,
            channels=1,
            rate=self.settings.input_sample_rate,
            input=True,
            frames_per_buffer=self.settings.input_chunk,
        )
        return self.input_stream

    def open_output(self):
        bit_size = (
            self.pyaudio_module.paInt16
            if self.settings.output_format == "pcm_s16le"
            else self.pyaudio_module.paFloat32
        )
        self.output_stream = self.pyaudio.open(
            format=bit_size,
            channels=1,
            rate=self.settings.output_sample_rate,
            output=True,
            frames_per_buffer=self.settings.output_chunk,
        )
        return self.output_stream

    def cleanup(self) -> None:
        for stream in (self.input_stream, self.output_stream):
            if stream is None:
                continue
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        self.pyaudio.terminate()


class RealtimeDialogService:
    """Owns microphone capture, realtime dialog socket, playback, and Live2D cues."""

    def __init__(
        self,
        settings: RealtimeDialogSettings | None = None,
        live2d: Live2DController | None = None,
        voice_system: VoiceSystem | None = None,
    ):
        self.settings = settings or RealtimeDialogSettings()
        self.live2d = live2d or Live2DController(AVATAR_SERVER_URL)
        self.voice_system = voice_system
        self._own_live2d = live2d is None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=128)
        self._speaking = False
        self._priority_active = False
        self._response_audio_finished = False
        self._playback_active = False
        self._playback_lock = threading.Lock()
        self._release_timer: threading.Timer | None = None

    def start(self) -> bool:
        if not self.settings.ready:
            logger.warning("实时语音未启动: REALTIME_DIALOG_APP_ID/ACCESS_KEY 未配置")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop_event.clear()
        if self._own_live2d:
            self.live2d.start()
        self._thread = threading.Thread(
            target=self._run_thread,
            name="RealtimeDialogThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("实时语音线程已启动")
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._release_timer is not None:
            self._release_timer.cancel()
            self._release_timer = None
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._speaking:
            self._end_speech()
        if self._own_live2d:
            self.live2d.stop()

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            logger.exception("实时语音服务退出: %s", exc)

    async def _run(self) -> None:
        audio_device = AudioDevice(self.settings)
        client = RealtimeDialogClient(self.settings, session_id=str(uuid.uuid4()))
        player = threading.Thread(
            target=self._playback_loop,
            args=(audio_device,),
            name="RealtimeDialogPlayer",
            daemon=True,
        )
        try:
            audio_device.open_output()
            audio_device.open_input()
            player.start()
            await client.connect()
            if self.settings.say_hello:
                await client.say_hello()
            await asyncio.gather(
                self._microphone_loop(audio_device, client),
                self._receive_loop(client),
            )
        finally:
            try:
                await client.finish_session()
                await client.finish_connection()
            except Exception:
                pass
            await client.close()
            self._audio_queue.put(None)
            player.join(timeout=3)
            audio_device.cleanup()
            logger.info("实时语音会话已关闭 logid=%s", client.logid)

    async def _microphone_loop(
        self,
        audio_device: AudioDevice,
        client: RealtimeDialogClient,
    ) -> None:
        logger.info("实时语音麦克风已打开，可以开始讲话")
        while not self._stop_event.is_set():
            try:
                audio = audio_device.input_stream.read(
                    self.settings.input_chunk,
                    exception_on_overflow=False,
                )
                await client.send_audio(audio)
                await asyncio.sleep(0.01)
            except Exception as exc:
                logger.warning("实时语音麦克风读取失败: %s", exc)
                await asyncio.sleep(0.1)

    async def _receive_loop(self, client: RealtimeDialogClient) -> None:
        while not self._stop_event.is_set():
            try:
                response = await asyncio.wait_for(client.receive(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            self._handle_response(response)
            event = response.get("event")
            if event in {152, 153}:
                self._stop_event.set()
                break

    def _handle_response(self, response: dict[str, Any]) -> None:
        if not response:
            return

        if (
            response.get("message_type") == "SERVER_ACK"
            and isinstance(response.get("payload_msg"), bytes)
        ):
            if not self._speaking:
                self._start_speech()
            try:
                self._audio_queue.put_nowait(response["payload_msg"])
            except queue.Full:
                logger.debug("实时语音播放队列已满，丢弃一段音频")
            return

        if response.get("message_type") == "SERVER_ERROR":
            logger.error("实时语音服务错误: %s", response.get("payload_msg"))
            self._stop_event.set()
            return

        event = response.get("event")
        if event == 450:
            self._activate_priority()
            self._response_audio_finished = False
            self._clear_pending_audio()
            self._end_visual_speech()
        elif event == 359:
            self._response_audio_finished = True
            self._release_priority_when_playback_idle()
        elif response.get("message_type") == "SERVER_FULL_RESPONSE":
            logger.debug("实时语音事件: %s", response)

    def _playback_loop(self, audio_device: AudioDevice) -> None:
        while not self._stop_event.is_set():
            try:
                audio = self._audio_queue.get(timeout=1)
            except queue.Empty:
                continue
            if audio is None:
                break
            try:
                with self._playback_lock:
                    self._playback_active = True
                audio_device.output_stream.write(audio)
            except Exception as exc:
                logger.warning("实时语音播放失败: %s", exc)
            finally:
                with self._playback_lock:
                    self._playback_active = False
                self._audio_queue.task_done()
                self._release_priority_when_playback_idle()

    def _clear_pending_audio(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.task_done()
            except queue.Empty:
                break

    def _start_speech(self) -> None:
        self._activate_priority()
        self._response_audio_finished = False
        self._speaking = True
        self.live2d.enqueue(
            "speech",
            {
                "event_type": "realtime_dialog",
                "name": self.settings.bot_name,
                "text": "正在和你实时对话…",
                "external_audio": True,
            },
        )

    def _end_speech(self) -> None:
        self._end_visual_speech()
        self._deactivate_priority()

    def _end_visual_speech(self) -> None:
        if not self._speaking:
            return
        self._speaking = False
        self.live2d.enqueue("speech_end", {"event_type": "realtime_dialog"})

    def _activate_priority(self) -> None:
        if self._release_timer is not None:
            self._release_timer.cancel()
            self._release_timer = None
        if self._priority_active:
            return
        self._priority_active = True
        if self.voice_system is not None:
            self.voice_system.set_realtime_dialog_active(True)

    def _deactivate_priority(self) -> None:
        if not self._priority_active:
            return
        self._priority_active = False
        if self.voice_system is not None:
            self.voice_system.set_realtime_dialog_active(False)

    def _release_priority_when_playback_idle(self) -> None:
        if not self._response_audio_finished or not self._priority_active:
            return
        with self._playback_lock:
            playback_active = self._playback_active
        if playback_active or not self._audio_queue.empty():
            return
        if self._release_timer is not None:
            self._release_timer.cancel()
        self._release_timer = threading.Timer(
            self.settings.release_grace_seconds,
            self._release_priority_if_still_idle,
        )
        self._release_timer.daemon = True
        self._release_timer.start()

    def _release_priority_if_still_idle(self) -> None:
        with self._playback_lock:
            playback_active = self._playback_active
        if playback_active or not self._audio_queue.empty():
            return
        self._end_speech()
