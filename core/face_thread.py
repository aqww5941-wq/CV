"""Camera worker thread that delegates recognition logic to RecognitionPipeline."""

from __future__ import annotations

import logging
import queue
import threading
import time

import cv2

from core.recognition_pipeline import PipelineResult, RecognitionPipeline

logger = logging.getLogger(__name__)


class FaceRecognitionThread(threading.Thread):
    """Owns camera reads; pipeline owns recognition, attendance, and events."""

    def __init__(
        self,
        cap: cv2.VideoCapture,
        pipeline: RecognitionPipeline,
        result_queue: queue.Queue[PipelineResult] | None = None,
    ):
        super().__init__(name="FaceRecognitionThread", daemon=True)
        self.cap = cap
        self.pipeline = pipeline
        self.result_queue = result_queue
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            result = self.pipeline.process_frame(frame)
            if self.result_queue is not None:
                self._publish_result(result)

    def _publish_result(self, result: PipelineResult) -> None:
        try:
            self.result_queue.put_nowait(result)
        except queue.Full:
            logger.debug("Face result dropped because queue is full")

