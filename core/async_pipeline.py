"""异步识别流水线: 摄像头读取 / 推理 / UI 渲染三线程解耦"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimedPipelineResult:
    result: object
    updated_at: float
    sequence: int


class AsyncPipelineWrapper:
    """将 RecognitionPipeline 的推理放入独立线程, 主线程只负责 UI 渲染。

    架构:
      摄像头线程(主线程) → 提交帧 → 推理线程 → 产出结果 → 主线程消费
      永远只处理最新帧, 推理慢就丢弃旧帧。
    """

    def __init__(self, pipeline):
        self._pipeline = pipeline
        self._frame_lock = threading.Lock()
        self._result_lock = threading.Lock()
        self._latest_frame = None
        self._latest_result: TimedPipelineResult | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame_ready = threading.Event()
        self._total_frames = 0
        self._processed_frames = 0
        self._dropped_frames = 0
        self._result_sequence = 0

    @property
    def stats(self) -> dict:
        return {
            "submitted": self._total_frames,
            "processed": self._processed_frames,
            "dropped": self._dropped_frames,
        }

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            name="AsyncRecognition",
            daemon=True,
        )
        self._thread.start()
        logger.info("异步识别流水线已启动")

    def stop(self) -> None:
        self._running = False
        self._frame_ready.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info(
            "异步识别流水线已停止 (提交=%d, 处理=%d, 丢弃=%d)",
            self._total_frames,
            self._processed_frames,
            self._dropped_frames,
        )

    def submit_frame(self, frame) -> None:
        with self._frame_lock:
            if self._latest_frame is not None:
                self._dropped_frames += 1
            self._latest_frame = frame
            self._total_frames += 1
            self._frame_ready.set()

    def get_result(self):
        with self._result_lock:
            return self._latest_result

    def _run(self) -> None:
        while self._running:
            self._frame_ready.wait(timeout=0.1)
            with self._frame_lock:
                if self._latest_frame is None:
                    self._frame_ready.clear()
                    continue
                frame = self._latest_frame
                self._latest_frame = None
                self._frame_ready.clear()

            try:
                result = self._pipeline.process_frame(frame)
                self._processed_frames += 1
            except Exception:
                logger.exception("异步推理异常")
                self._dropped_frames += 1
                continue

            with self._result_lock:
                self._result_sequence += 1
                self._latest_result = TimedPipelineResult(
                    result=result,
                    updated_at=time.time(),
                    sequence=self._result_sequence,
                )
