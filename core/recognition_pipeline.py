"""Shared face recognition -> attendance -> event pipeline."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from config import (
    ALLOW_REPEAT_CHECKIN,
    CROWD_THRESHOLD,
    IDLE_LONG_THRESHOLD,
    REPEAT_FEEDBACK_COOLDOWN_SECONDS,
    STRANGER_MIN_UNKNOWN_HITS,
)
from core.attendance_db import AttendanceDB
from core.checkin import CheckInTracker
from core.embedding_matcher import EmbeddingMatcher
from core.events import EventBus
from core.face_utils import is_complete_face_for_stranger
from core.recognition_cache import RecognitionCache
from core.recognizer import FaceRecognizer
from core.tracker import FaceTracker
from core.vote import VoteBuffer

logger = logging.getLogger(__name__)


@dataclass
class ProcessedFace:
    bbox: list[int]
    track_id: int
    name: str | None
    similarity: float
    recognized: bool
    label: str
    checked_in_now: bool = False


@dataclass
class PipelineResult:
    faces: list[ProcessedFace]
    face_count: int
    checked_in_names: list[str] = field(default_factory=list)


class RecognitionPipeline:
    """Owns shared recognition, voting, attendance, and behavior event logic."""

    def __init__(
        self,
        recognizer: FaceRecognizer,
        tracker: FaceTracker,
        db_embeddings: list,
        attendance_db: AttendanceDB,
        checkin_tracker: CheckInTracker,
        vote_buffer: VoteBuffer,
        rec_cache: RecognitionCache,
        event_bus: EventBus,
    ):
        self.recognizer = recognizer
        self.tracker = tracker
        self.db_embeddings = db_embeddings
        self.matcher = EmbeddingMatcher(db_embeddings)
        self.attendance_db = attendance_db
        self.checkin_tracker = checkin_tracker
        self.vote_buffer = vote_buffer
        self.rec_cache = rec_cache
        self.event_bus = event_bus

        self.last_face_time = 0.0
        self.idle_long_sent = False
        self.crowd_sent = False
        self.repeat_feedback_times: dict[str, float] = {}
        self.unknown_hits: dict[int, int] = {}
        self.pending_checkins: set[str] = set()
        self.pending_lock = threading.Lock()
        self.attendance_lock = threading.Lock()
        self.attendance_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="AttendanceWorker",
        )

    def update_embeddings(self, db_embeddings: list) -> None:
        self.db_embeddings = db_embeddings
        self.matcher.update(db_embeddings)

    def shutdown(self) -> None:
        self.attendance_executor.shutdown(wait=False, cancel_futures=True)

    def process_frame(self, frame) -> PipelineResult:
        now = time.time()
        faces = self.tracker.update(frame, self.recognizer)
        active_ids = {face["track_id"] for face in faces}
        self.vote_buffer.cleanup_inactive(active_ids)
        self.rec_cache.cleanup(active_ids)
        self._cleanup_unknown_hits(active_ids)
        self._handle_scene_events(len(faces), now)

        processed: list[ProcessedFace] = []
        checked_in_names: list[str] = []

        for face in faces:
            item = self._process_face(face, frame.shape, now)
            processed.append(item)
            if item.checked_in_now and item.name:
                checked_in_names.append(item.name)

        return PipelineResult(
            faces=processed,
            face_count=len(faces),
            checked_in_names=checked_in_names,
        )

    def checkout(self, name: str) -> int | None:
        with self.attendance_lock:
            duration = self.attendance_db.check_out(name)
        self.checkin_tracker.reset_checkin(name)
        self.event_bus.checkout(name, 0, duration or 0)
        return duration

    def _cleanup_unknown_hits(self, active_ids: set[int]) -> None:
        for track_id in list(self.unknown_hits.keys()):
            if track_id not in active_ids:
                self.unknown_hits.pop(track_id, None)

    def _handle_scene_events(self, face_count: int, now: float) -> None:
        if face_count > 0:
            if self.last_face_time == 0.0 or self.idle_long_sent:
                self.event_bus.attention()
                self.last_face_time = 0.0
            self.idle_long_sent = False
            self.last_face_time = now

            if face_count >= CROWD_THRESHOLD and not self.crowd_sent:
                self.event_bus.crowd(face_count)
                self.crowd_sent = True
            elif face_count < CROWD_THRESHOLD:
                self.crowd_sent = False
            return

        if (
            self.last_face_time > 0
            and now - self.last_face_time > IDLE_LONG_THRESHOLD
            and not self.idle_long_sent
        ):
            self.event_bus.idle_long()
            self.idle_long_sent = True

    def _process_face(self, face: dict, frame_shape, now: float) -> ProcessedFace:
        bbox = face["bbox"]
        track_id = face["track_id"]
        name, similarity = self._recognize(track_id, face["embedding"])
        similarity = float(similarity or 0.0)

        if name is None:
            return self._handle_unknown_face(bbox, track_id, similarity, frame_shape)

        return self._handle_recognized_face(name, similarity, bbox, track_id, now)

    def _recognize(self, track_id: int, embedding) -> tuple[str | None, float]:
        name, similarity = self.rec_cache.get(track_id)
        if name is not None:
            return name, float(similarity or 0.0)

        name, similarity = self.matcher.match(embedding)
        if name is not None:
            self.rec_cache.set(track_id, name, similarity)
        return name, float(similarity or 0.0)

    def _handle_unknown_face(
        self,
        bbox: list[int],
        track_id: int,
        similarity: float,
        frame_shape,
    ) -> ProcessedFace:
        complete_face = is_complete_face_for_stranger(bbox, frame_shape)
        if complete_face:
            self.unknown_hits[track_id] = self.unknown_hits.get(track_id, 0) + 1
        else:
            self.unknown_hits[track_id] = 0

        if (
            complete_face
            and self.unknown_hits.get(track_id, 0) >= STRANGER_MIN_UNKNOWN_HITS
            and self.recognizer.should_log_stranger()
        ):
            self.event_bus.stranger()
            logger.info("检测到未知访客")

        return ProcessedFace(
            bbox=bbox,
            track_id=track_id,
            name=None,
            similarity=similarity,
            recognized=False,
            label="未知访客" if complete_face else "请正对摄像头",
        )

    def _handle_recognized_face(
        self,
        name: str,
        similarity: float,
        bbox: list[int],
        track_id: int,
        now: float,
    ) -> ProcessedFace:
        try:
            if not ALLOW_REPEAT_CHECKIN and self.checkin_tracker.is_checked_out_today(name):
                return self._face(bbox, track_id, name, similarity, f"已签退 · {name}")

            if not ALLOW_REPEAT_CHECKIN and self.checkin_tracker.is_checked_in_today(name):
                self._maybe_repeat_feedback(name, now)
                return self._face(bbox, track_id, name, similarity, f"已签到 · {name}")

            if self._is_pending_checkin(name):
                return self._face(bbox, track_id, name, similarity, f"签到中 · {name}")

            voted_name = self.vote_buffer.vote(track_id, name, similarity, now)
            if voted_name is None:
                return self._face(bbox, track_id, name, similarity, name)

            self._add_pending_checkin(voted_name)
            self.attendance_executor.submit(
                self._complete_checkin,
                voted_name,
                similarity,
            )
            return self._face(
                bbox,
                track_id,
                voted_name,
                similarity,
                f"已签到 · {voted_name}",
                checked_in_now=True,
            )
        except Exception as exc:
            logger.warning("人脸业务处理失败 (%s): %s", name, exc)
            return self._face(bbox, track_id, name, similarity, f"处理中 · {name}")

    def _complete_checkin(self, name: str, similarity: float) -> None:
        try:
            with self.attendance_lock:
                is_first = not self.attendance_db.has_any_record(name)
                is_returning = not is_first and not self.attendance_db.has_record_today(
                    name,
                    before_now=True,
                )
                row_id = self.attendance_db.check_in(name)
            self.checkin_tracker.mark_checked_in(name)
            self.event_bus.checkin(
                name,
                row_id,
                similarity,
                is_first=is_first,
                is_returning=is_returning,
            )
            logger.info(
                "签到成功: %s (sim=%.3f, row=%s, first=%s, returning=%s)",
                name,
                similarity,
                row_id,
                is_first,
                is_returning,
            )
        except Exception as exc:
            logger.warning("签到落库失败 (%s): %s", name, exc)
        finally:
            self._discard_pending_checkin(name)

    def _is_pending_checkin(self, name: str) -> bool:
        with self.pending_lock:
            return name in self.pending_checkins

    def _add_pending_checkin(self, name: str) -> None:
        with self.pending_lock:
            self.pending_checkins.add(name)

    def _discard_pending_checkin(self, name: str) -> None:
        with self.pending_lock:
            self.pending_checkins.discard(name)

    def _maybe_repeat_feedback(self, name: str, now: float) -> None:
        last_repeat = self.repeat_feedback_times.get(name, 0.0)
        if now - last_repeat >= REPEAT_FEEDBACK_COOLDOWN_SECONDS:
            self.event_bus.repeat_checkin(name)
            self.repeat_feedback_times[name] = now

    @staticmethod
    def _face(
        bbox: list[int],
        track_id: int,
        name: str,
        similarity: float,
        label: str,
        checked_in_now: bool = False,
    ) -> ProcessedFace:
        return ProcessedFace(
            bbox=bbox,
            track_id=track_id,
            name=name,
            similarity=similarity,
            recognized=True,
            label=label,
            checked_in_now=checked_in_now,
        )
