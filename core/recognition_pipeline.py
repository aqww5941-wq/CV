"""Shared face recognition -> attendance -> event pipeline."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from config import (
    ALLOW_REPEAT_CHECKIN,
    CROWD_THRESHOLD,
    IDLE_LONG_THRESHOLD,
    MAX_PROCESS_FACES,
    REPEAT_FEEDBACK_COOLDOWN_SECONDS,
    UNKNOWN_ENROLL_MAX_EMPLOYEE_SIMILARITY,
    UNKNOWN_ENROLL_MIN_HITS,
    STRANGER_MIN_UNKNOWN_HITS,
)
from core.attendance_db import AttendanceDB
from core.embedding_matcher import EmbeddingMatcher
from core.events import EventBus
from core.face_utils import (
    can_enroll_unknown_visitor,
    check_face_quality,
    is_complete_face_for_stranger,
)
from core.gender import gender_display_name, gender_salutation
from core.recognition_cache import RecognitionCache
from core.recognizer import FaceRecognizer
from core.tracker import FaceTrackerABC
from core.unknown_visitors import UnknownVisitorStore
from core.vote import VoteBuffer

logger = logging.getLogger(__name__)


class CheckInStateStore(Protocol):
    def is_checked_in_today(self, name: str) -> bool: ...

    def is_checked_out_today(self, name: str) -> bool: ...

    def mark_checked_in(self, name: str) -> None: ...

    def reset_checkin(self, name: str) -> None: ...


@dataclass
class ProcessedFace:
    bbox: list[int]
    track_id: int
    name: str | None
    similarity: float
    recognized: bool
    label: str
    checked_in_now: bool = False
    unknown_visitor_id: str | None = None
    returning_unknown: bool = False
    gender: str | None = None


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
        tracker: FaceTrackerABC,
        db_embeddings: list,
        attendance_db: AttendanceDB,
        checkin_tracker: CheckInStateStore,
        vote_buffer: VoteBuffer,
        rec_cache: RecognitionCache,
        event_bus: EventBus,
        unknown_visitors: UnknownVisitorStore,
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
        self.unknown_visitors = unknown_visitors

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
        needs_fresh_detection = False

        for face in self._select_business_faces(faces, frame.shape):
            item = self._process_face(face, frame.shape, now)
            processed.append(item)
            if item.checked_in_now and item.name:
                checked_in_names.append(item.name)
            if self._needs_more_detection(item):
                needs_fresh_detection = True

        if needs_fresh_detection:
            self.tracker.request_detection()

        return PipelineResult(
            faces=processed,
            face_count=len(faces),
            checked_in_names=checked_in_names,
        )

    @staticmethod
    def _select_business_faces(faces: list[dict], frame_shape) -> list[dict]:
        if MAX_PROCESS_FACES <= 0 or len(faces) <= MAX_PROCESS_FACES:
            return faces

        frame_h, frame_w = frame_shape[:2]
        frame_cx = frame_w / 2.0
        frame_cy = frame_h / 2.0

        def priority(face: dict) -> tuple[int, float]:
            x1, y1, x2, y2 = face["bbox"]
            width = max(0, x2 - x1)
            height = max(0, y2 - y1)
            area = width * height
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            center_distance = ((cx - frame_cx) ** 2 + (cy - frame_cy) ** 2) ** 0.5
            return (-area, center_distance)

        return sorted(faces, key=priority)[:MAX_PROCESS_FACES]

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
        quality = check_face_quality(face, frame_shape)
        if not quality.passed:
            self.unknown_hits[track_id] = 0
            return ProcessedFace(
                bbox=bbox,
                track_id=track_id,
                name=None,
                similarity=0.0,
                recognized=False,
                label=quality.label,
            )

        fresh_detection = face.get("fresh_detection", True)
        name, similarity, decision = self._recognize(
            track_id,
            face["embedding"],
            fresh_detection=fresh_detection,
        )
        similarity = float(similarity or 0.0)

        if name is None:
            return self._handle_unknown_face(
                face,
                bbox,
                track_id,
                similarity,
                frame_shape,
            )

        return self._handle_recognized_face(
            name,
            similarity,
            bbox,
            track_id,
            now,
            decision,
            fresh_detection,
            face["embedding"],
        )

    def _recognize(
        self,
        track_id: int,
        embedding,
        fresh_detection: bool,
    ) -> tuple[str | None, float, str]:
        name, similarity = self.rec_cache.get_known(track_id)
        if name is not None:
            return name, float(similarity or 0.0), "cached"

        known_miss_similarity = self.rec_cache.get_known_miss(track_id, embedding)
        if known_miss_similarity is not None:
            return None, known_miss_similarity, "reject"

        candidate = self.matcher.match_candidate(embedding)
        if candidate.decision == "reject" and fresh_detection:
            self.rec_cache.set_known_miss(track_id, candidate.similarity, embedding)
        elif candidate.decision == "review":
            logger.debug(
                "识别进入复核区: %s sim=%.3f",
                candidate.name,
                candidate.similarity,
            )
        return candidate.name, float(candidate.similarity or 0.0), candidate.decision

    def _handle_unknown_face(
        self,
        face: dict,
        bbox: list[int],
        track_id: int,
        similarity: float,
        frame_shape,
    ) -> ProcessedFace:
        complete_face = is_complete_face_for_stranger(bbox, frame_shape)
        fresh_detection = face.get("fresh_detection", True)
        if complete_face and fresh_detection:
            self.unknown_hits[track_id] = self.unknown_hits.get(track_id, 0) + 1
        elif not complete_face:
            self.unknown_hits[track_id] = 0

        visitor = None
        can_enroll = self._can_enroll_unknown_visitor(
            face,
            frame_shape,
            similarity,
            track_id,
        )

        if can_enroll and fresh_detection:
            visitor = self.rec_cache.get_unknown(track_id, face["embedding"])
            if visitor is None:
                visitor = self.unknown_visitors.match_or_create(
                    face["embedding"],
                    gender=face.get("gender"),
                )
                self.rec_cache.set_unknown(
                    track_id,
                    visitor.visitor_id,
                    visitor.label,
                    visitor.similarity,
                    visitor.is_returning,
                    visitor.gender,
                    face["embedding"],
                )

            if self.recognizer.should_log_stranger():
                effective_gender = visitor.gender or face.get("gender")
                salutation = gender_salutation(effective_gender)
                self.event_bus.stranger(
                    visitor_label=visitor.label,
                    is_returning=visitor.is_returning,
                    gender=effective_gender,
                    salutation=salutation,
                )
                logger.info(
                    "检测到%s: %s, %s (sim=%.3f)",
                    "回访未知访客" if visitor.is_returning else "新未知访客",
                    visitor.label,
                    gender_display_name(effective_gender),
                    visitor.similarity,
                )
        elif (
            complete_face
            and fresh_detection
            and self.unknown_hits.get(track_id, 0) >= STRANGER_MIN_UNKNOWN_HITS
            and self.recognizer.should_log_stranger()
        ):
            gender = face.get("gender")
            self.event_bus.stranger(
                gender=gender,
                salutation=gender_salutation(gender),
            )
            logger.info(
                "检测到未知访客但未入库: sim=%.3f, hits=%d, gender=%s",
                similarity,
                self.unknown_hits.get(track_id, 0),
                gender_display_name(gender),
            )

        if complete_face and not fresh_detection:
            label = "识别中"
        else:
            label = self._unknown_label(visitor, complete_face)
        result_gender = (
            visitor.gender or face.get("gender") if visitor else face.get("gender")
        )

        return ProcessedFace(
            bbox=bbox,
            track_id=track_id,
            name=None,
            similarity=similarity,
            recognized=False,
            label=label,
            unknown_visitor_id=visitor.visitor_id if visitor else None,
            returning_unknown=visitor.is_returning if visitor else False,
            gender=result_gender,
        )

    @staticmethod
    def _unknown_label(visitor, complete_face: bool) -> str:
        if visitor is None:
            return "未知访客" if complete_face else "请正对摄像头"
        if visitor.is_returning:
            return f"{visitor.label} · 又见面"
        return f"{visitor.label} · 初次记录"

    def _can_enroll_unknown_visitor(
        self,
        face: dict,
        frame_shape,
        employee_similarity: float,
        track_id: int,
    ) -> bool:
        if self.unknown_hits.get(track_id, 0) < UNKNOWN_ENROLL_MIN_HITS:
            return False
        if employee_similarity >= UNKNOWN_ENROLL_MAX_EMPLOYEE_SIMILARITY:
            return False
        return can_enroll_unknown_visitor(face, frame_shape)

    def _handle_recognized_face(
        self,
        name: str,
        similarity: float,
        bbox: list[int],
        track_id: int,
        now: float,
        decision: str = "accept",
        fresh_detection: bool = True,
        embedding=None,
    ) -> ProcessedFace:
        try:
            vote_confirmed = False
            if decision in {"accept", "review"}:
                if not fresh_detection:
                    return self._face(
                        bbox,
                        track_id,
                        name,
                        similarity,
                        f"确认中 · {name}",
                    )
                voted_name = self.vote_buffer.vote(track_id, name, similarity, now)
                if voted_name is None:
                    return self._face(
                        bbox,
                        track_id,
                        name,
                        similarity,
                        f"确认中 · {name}",
                    )
                name = voted_name
                vote_confirmed = True
                if embedding is not None:
                    self.rec_cache.set_known(
                        track_id,
                        name,
                        similarity,
                        embedding,
                    )

            if not ALLOW_REPEAT_CHECKIN and self.checkin_tracker.is_checked_out_today(
                name
            ):
                return self._face(bbox, track_id, name, similarity, f"已签退 · {name}")

            if not ALLOW_REPEAT_CHECKIN and self.checkin_tracker.is_checked_in_today(
                name
            ):
                self._maybe_repeat_feedback(name, now)
                return self._face(bbox, track_id, name, similarity, f"已签到 · {name}")

            if self._is_pending_checkin(name):
                return self._face(bbox, track_id, name, similarity, f"签到中 · {name}")

            voted_name = name if vote_confirmed or decision == "cached" else None
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

    @staticmethod
    def _needs_more_detection(face: ProcessedFace) -> bool:
        return face.label.startswith("确认中") or face.label == "识别中"
