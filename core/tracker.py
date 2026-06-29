"""人脸跟踪: 抽象接口 + OpenCV / ByteTrack 双后端实现。

ByteTrack 适用于多人进出、遮挡、短暂离开再回来的场景，
track_id 稳定性优于 OpenCV KCF/CSRT 单目标跟踪器。

架构:
  FaceTrackerABC          -- 抽象接口
  OpenCVFaceTracker       -- 现有 OpenCV 轻跟踪 (KCF/CSRT/MIL)
  ByteTrackFaceTracker    -- ByteTrack 风格 (Kalman + IoU 关联)
  FaceTracker(backend=...) -- 工厂函数
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import cv2
import numpy as np

from config import (
    BYTETRACK_DETECT_INTERVAL,
    BYTETRACK_TRACK_BUFFER,
    BYTETRACK_MATCH_THRESHOLD,
    DETECT_INTERVAL,
    OPENCV_TRACKER_TYPE,
    TRACKER_BACKEND,
)

logger = logging.getLogger(__name__)

TRACKER_STALE_SECONDS = 2.0

# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------


class FaceTrackerABC(ABC):
    """人脸跟踪器抽象接口。

    所有后端实现必须输出统一的 dict 格式:
        {
            "bbox": [x1, y1, x2, y2],
            "embedding": np.ndarray | None,
            "det_score": float,
            "kps": list | None,
            "gender": str | None,
            "track_id": int,
            "fresh_detection": bool,
        }
    """

    @abstractmethod
    def update(self, frame, recognizer) -> list[dict]:
        """处理一帧, 返回当前活跃的 track 列表。"""
        ...

    @abstractmethod
    def request_detection(self) -> None:
        """请求下一次 update 执行完整检测。"""
        ...


# ---------------------------------------------------------------------------
# 工具函数 (两种后端共享)
# ---------------------------------------------------------------------------


def _iou(box_a: list[int], box_b: list[int]) -> float:
    xa1, ya1, xa2, ya2 = box_a
    xb1, yb1, xb2, yb2 = box_b
    inter_x1 = max(xa1, xb1)
    inter_y1 = max(ya1, yb1)
    inter_x2 = min(xa2, xb2)
    inter_y2 = min(ya2, yb2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    area_a = (xa2 - xa1) * (ya2 - ya1)
    area_b = (xb2 - xb1) * (yb2 - yb1)
    union_area = area_a + area_b - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def _center_score(box_a: list[int], box_b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
    bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
    distance = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
    scale = max(ax2 - ax1, ay2 - ay1, bx2 - bx1, by2 - by1, 1)
    return max(0.0, 1.0 - distance / scale)


def _bbox_to_tracker_box(bbox: list[int], frame_w: int, frame_h: int):
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(frame_w - 1, int(x1)))
    y1 = max(0, min(frame_h - 1, int(y1)))
    x2 = max(0, min(frame_w - 1, int(x2)))
    y2 = max(0, min(frame_h - 1, int(y2)))
    box_w = x2 - x1
    box_h = y2 - y1
    if box_w < 2 or box_h < 2:
        return None
    return (x1, y1, box_w, box_h)


def _tracker_box_to_bbox(box, frame_w: int, frame_h: int) -> list[int] | None:
    x, y, box_w, box_h = box
    x1 = max(0, min(frame_w - 1, int(round(x))))
    y1 = max(0, min(frame_h - 1, int(round(y))))
    x2 = max(0, min(frame_w - 1, int(round(x + box_w))))
    y2 = max(0, min(frame_h - 1, int(round(y + box_h))))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return [x1, y1, x2, y2]


def _match_detections_to_tracks(
    detections: list[dict],
    tracks: list[dict],
    iou_threshold: float,
) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    """贪心 IoU 匹配: 返回 (匹配对列表, 未匹配检测索引集合, 未匹配 track 索引集合)。"""
    if not detections or not tracks:
        return (
            [],
            set(range(len(detections))),
            set(range(len(tracks))),
        )

    pairs = []
    for i, det in enumerate(detections):
        for j, track in enumerate(tracks):
            score = max(
                _iou(det["bbox"], track["bbox"]),
                _center_score(det["bbox"], track["bbox"]),
            )
            if score >= iou_threshold:
                pairs.append((score, i, j))
    pairs.sort(key=lambda x: x[0], reverse=True)

    matched_det: set[int] = set()
    matched_track: set[int] = set()
    matches: list[tuple[int, int]] = []

    for score, i, j in pairs:
        if i not in matched_det and j not in matched_track:
            matches.append((i, j))
            matched_det.add(i)
            matched_track.add(j)

    unmatched_det = set(range(len(detections))) - matched_det
    unmatched_track = set(range(len(tracks))) - matched_track
    return matches, unmatched_det, unmatched_track


# ---------------------------------------------------------------------------
# OpenCV 后端 (现有实现, 重命名)
# ---------------------------------------------------------------------------


class OpenCVFaceTracker(FaceTrackerABC):
    """检测 + IOU 关联 + OpenCV 单目标轻跟踪。

    lost_frames 表示连续几次检测没有匹配到，不代表中间复用缓存的帧数。
    """

    def __init__(
        self,
        detect_interval: int = DETECT_INTERVAL,
        iou_threshold: float = 0.3,
        max_lost_frames: int = 2,
    ):
        self._detect_interval = detect_interval
        self._iou_threshold = iou_threshold
        self._max_lost_frames = max_lost_frames
        self._frame_count = 0
        self._next_track_id = 1
        self._tracks: list[dict] = []
        self._tracker_warning_logged = False
        self._force_detect_once = False

    def update(self, frame, recognizer) -> list[dict]:
        self._frame_count += 1
        should_detect = (
            self._force_detect_once
            or self._frame_count % self._detect_interval == 1
            or not self._tracks
        )
        self._force_detect_once = False
        if should_detect:
            detections = recognizer.detect(frame)
            self._associate(detections, frame)
        else:
            self._track_frame(frame)
        return [
            {
                "bbox": t["bbox"],
                "embedding": t["embedding"],
                "det_score": t["det_score"],
                "kps": t.get("kps"),
                "gender": t.get("gender"),
                "track_id": t["track_id"],
                "fresh_detection": t.get("fresh_detection", False),
            }
            for t in self._tracks
            if t["lost_frames"] == 0
        ]

    def request_detection(self) -> None:
        self._force_detect_once = True

    def _associate(self, detections: list[dict], frame) -> None:
        matches, unmatched_det, unmatched_track = _match_detections_to_tracks(
            detections, self._tracks, self._iou_threshold
        )

        for det_idx, track_idx in matches:
            det = detections[det_idx]
            track = self._tracks[track_idx]
            track["bbox"] = det["bbox"]
            track["embedding"] = det["embedding"]
            track["det_score"] = det["det_score"]
            track["kps"] = det.get("kps")
            track["gender"] = det.get("gender")
            track["lost_frames"] = 0
            track["fresh_detection"] = True
            track["last_detected_at"] = time.time()
            track["tracker"] = self._init_cv_tracker(frame, det["bbox"])

        for det_idx in unmatched_det:
            det = detections[det_idx]
            track_id = self._next_track_id
            self._tracks.append(
                {
                    "track_id": track_id,
                    "bbox": det["bbox"],
                    "embedding": det["embedding"],
                    "det_score": det["det_score"],
                    "kps": det.get("kps"),
                    "gender": det.get("gender"),
                    "lost_frames": 0,
                    "fresh_detection": True,
                    "last_detected_at": time.time(),
                    "tracker": self._init_cv_tracker(frame, det["bbox"]),
                }
            )
            self._next_track_id += 1

        for track_idx in unmatched_track:
            self._tracks[track_idx]["lost_frames"] += 1

        self._prune_lost_tracks()

    def _track_frame(self, frame) -> None:
        h, w = frame.shape[:2]
        now = time.time()
        for track in self._tracks:
            track["fresh_detection"] = False
            if now - float(track.get("last_detected_at", 0.0)) > TRACKER_STALE_SECONDS:
                track["lost_frames"] += 1
                continue
            tracker = track.get("tracker")
            if tracker is None:
                if not self._tracker_warning_logged:
                    logger.warning(
                        "OpenCV tracker 不可用，建议安装 opencv-contrib-python "
                        "以启用 KCF/CSRT 轻跟踪"
                    )
                    self._tracker_warning_logged = True
                continue

            ok, box = tracker.update(frame)
            if not ok:
                track["lost_frames"] += 1
                continue

            bbox = _tracker_box_to_bbox(box, w, h)
            if bbox is None:
                track["lost_frames"] += 1
                continue

            track["bbox"] = bbox
            track["lost_frames"] = 0

        self._prune_lost_tracks()

    def _prune_lost_tracks(self) -> None:
        self._tracks = [
            t for t in self._tracks if t["lost_frames"] <= self._max_lost_frames
        ]
        if not self._tracks:
            self._next_track_id = 1

    def _init_cv_tracker(self, frame, bbox: list[int]):
        tracker = self._create_cv_tracker()
        if tracker is None:
            return None

        h, w = frame.shape[:2]
        tracker_box = _bbox_to_tracker_box(bbox, w, h)
        if tracker_box is None:
            return None

        try:
            tracker.init(frame, tracker_box)
            return tracker
        except cv2.error as exc:
            logger.debug("OpenCV tracker 初始化失败: %s", exc)
            return None

    def _create_cv_tracker(self):
        tracker_type = OPENCV_TRACKER_TYPE.upper()
        factories = (
            f"Tracker{tracker_type}_create",
            "TrackerKCF_create",
            "TrackerCSRT_create",
            "TrackerMIL_create",
        )
        for factory in factories:
            create = getattr(cv2, factory, None)
            if create is not None:
                return create()
            legacy = getattr(cv2, "legacy", None)
            create = getattr(legacy, factory, None) if legacy is not None else None
            if create is not None:
                return create()
        return None


# ---------------------------------------------------------------------------
# ByteTrack 后端
# ---------------------------------------------------------------------------


@dataclass
class _ByteTrackState:
    """ByteTrack 单条轨迹的 Kalman 状态。"""

    track_id: int
    state: np.ndarray
    covariance: np.ndarray
    embedding: np.ndarray | None = None
    det_score: float = 0.0
    kps: list | None = None
    gender: str | None = None
    lost_frames: int = 0
    total_frames: int = 0
    last_detected_at: float = 0.0
    fresh_detection: bool = False

    @property
    def bbox(self) -> list[int]:
        x, y, w, h = (
            self.state[0, 0],
            self.state[1, 0],
            self.state[2, 0],
            self.state[3, 0],
        )
        x1 = int(round(x))
        y1 = int(round(y))
        x2 = int(round(x + w))
        y2 = int(round(y + h))
        return [x1, y1, x2, y2]


class ByteTrackFaceTracker(FaceTrackerABC):
    """ByteTrack 风格的多目标跟踪器。

    核心思路:
    - 检测帧: 调用 SCRFD 获取检测框 + embedding，用 IoU 贪心关联到已有 track
    - 非检测帧: 用 Kalman 滤波预测 track 位置，维持 track_id 连续性
    - 身份确认仍只认 fresh_detection 的 embedding，避免预测帧污染识别

    相比 OpenCV KCF/CSRT:
    - track_id 更稳定 (基于检测框关联而非像素跟踪)
    - 遮挡/短暂离开后恢复更好
    - 需要更高检测频率 (建议 3-5 帧一次)
    """

    STATE_DIM = 8
    MEAS_DIM = 4

    def __init__(
        self,
        detect_interval: int = BYTETRACK_DETECT_INTERVAL,
        track_buffer: int = BYTETRACK_TRACK_BUFFER,
        iou_threshold: float = BYTETRACK_MATCH_THRESHOLD,
    ):
        self._detect_interval = detect_interval
        self._track_buffer = track_buffer
        self._iou_threshold = iou_threshold
        self._frame_count = 0
        self._next_track_id = 1
        self._tracks: list[_ByteTrackState] = []
        self._force_detect_once = False

        self._init_kalman_matrices()

    def _init_kalman_matrices(self) -> None:
        self._F = np.eye(self.STATE_DIM, dtype=np.float64)
        self._F[0, 4] = 1.0
        self._F[1, 5] = 1.0
        self._F[2, 6] = 1.0
        self._F[3, 7] = 1.0

        self._H = np.zeros((self.MEAS_DIM, self.STATE_DIM), dtype=np.float64)
        self._H[0, 0] = 1.0
        self._H[1, 1] = 1.0
        self._H[2, 2] = 1.0
        self._H[3, 3] = 1.0

        self._Q = np.eye(self.STATE_DIM, dtype=np.float64) * 0.01
        self._Q[4:, 4:] *= 0.01

        self._R = np.eye(self.MEAS_DIM, dtype=np.float64) * 0.1

        self._I = np.eye(self.STATE_DIM, dtype=np.float64)

    def update(self, frame, recognizer) -> list[dict]:
        self._frame_count += 1
        should_detect = (
            self._force_detect_once
            or self._frame_count % self._detect_interval == 1
            or not self._tracks
        )
        self._force_detect_once = False

        if should_detect:
            detections = recognizer.detect(frame)
            self._associate(detections)
        else:
            self._predict_only()

        self._prune_dead_tracks()
        return self._collect_output()

    def request_detection(self) -> None:
        self._force_detect_once = True

    # ------------------------------------------------------------------
    # 关联逻辑
    # ------------------------------------------------------------------

    def _associate(self, detections: list[dict]) -> None:
        self._predict_all()

        track_dicts = [{"bbox": t.bbox, "track_id": t.track_id} for t in self._tracks]
        matches, unmatched_det, unmatched_track = _match_detections_to_tracks(
            detections, track_dicts, self._iou_threshold
        )

        for det_idx, track_idx in matches:
            det = detections[det_idx]
            track = self._tracks[track_idx]
            self._update_track(track, det)

        for det_idx in unmatched_det:
            det = detections[det_idx]
            track = self._create_track(det)
            self._tracks.append(track)

        for track_idx in sorted(unmatched_track, reverse=True):
            self._tracks[track_idx].lost_frames += 1
            self._tracks[track_idx].fresh_detection = False

    # ------------------------------------------------------------------
    # Kalman 滤波
    # ------------------------------------------------------------------

    @staticmethod
    def _init_state_from_bbox(bbox: list[int]) -> np.ndarray:
        x1, y1, x2, y2 = bbox
        state = np.zeros((ByteTrackFaceTracker.STATE_DIM, 1), dtype=np.float64)
        state[0, 0] = float(x1)
        state[1, 0] = float(y1)
        state[2, 0] = max(1.0, float(x2 - x1))
        state[3, 0] = max(1.0, float(y2 - y1))
        return state

    def _predict_all(self) -> None:
        for track in self._tracks:
            self._predict_track(track)

    def _predict_track(self, track: _ByteTrackState) -> None:
        track.state = self._F @ track.state
        track.covariance = self._F @ track.covariance @ self._F.T + self._Q
        track.fresh_detection = False

    def _predict_only(self) -> None:
        for track in self._tracks:
            track.fresh_detection = False
            self._predict_track(track)

    def _update_track(self, track: _ByteTrackState, det: dict) -> None:
        z = self._init_state_from_bbox(det["bbox"])[: self.MEAS_DIM]

        y = z - self._H @ track.state
        S = self._H @ track.covariance @ self._H.T + self._R
        try:
            K = track.covariance @ self._H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            logger.debug("Kalman 增益矩阵奇异，跳过 track %d 的更新", track.track_id)
            return

        track.state = track.state + K @ y
        track.covariance = (self._I - K @ self._H) @ track.covariance

        track.embedding = det["embedding"]
        track.det_score = det["det_score"]
        track.kps = det.get("kps")
        track.gender = det.get("gender")
        track.lost_frames = 0
        track.total_frames += 1
        track.last_detected_at = time.time()
        track.fresh_detection = True

    def _create_track(self, det: dict) -> _ByteTrackState:
        state = self._init_state_from_bbox(det["bbox"])
        P = np.eye(self.STATE_DIM, dtype=np.float64) * 10.0
        track_id = self._next_track_id
        self._next_track_id += 1

        return _ByteTrackState(
            track_id=track_id,
            state=state,
            covariance=P,
            embedding=det["embedding"],
            det_score=det["det_score"],
            kps=det.get("kps"),
            gender=det.get("gender"),
            total_frames=1,
            last_detected_at=time.time(),
            fresh_detection=True,
        )

    # ------------------------------------------------------------------
    # 输出 & 清理
    # ------------------------------------------------------------------

    def _prune_dead_tracks(self) -> None:
        self._tracks = [t for t in self._tracks if t.lost_frames <= self._track_buffer]
        if not self._tracks:
            self._next_track_id = 1

    def _collect_output(self) -> list[dict]:
        return [
            {
                "bbox": t.bbox,
                "embedding": t.embedding,
                "det_score": t.det_score,
                "kps": t.kps,
                "gender": t.gender,
                "track_id": t.track_id,
                "fresh_detection": t.fresh_detection,
            }
            for t in self._tracks
            if t.lost_frames == 0
        ]


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def FaceTracker(
    backend: str | None = None,
    **kwargs,
) -> FaceTrackerABC:
    """创建人脸跟踪器实例。

    Args:
        backend: "opencv" | "bytetrack" | None (默认读 TRACKER_BACKEND 环境变量)
        **kwargs: 传递给具体后端构造函数的参数

    Returns:
        FaceTrackerABC 实例
    """
    backend = (backend or TRACKER_BACKEND).strip().lower()

    if backend == "bytetrack":
        logger.info("跟踪器后端: ByteTrack (Kalman + IoU 关联)")
        return ByteTrackFaceTracker(**kwargs)

    logger.info("跟踪器后端: OpenCV (%s)", OPENCV_TRACKER_TYPE)
    return OpenCVFaceTracker(**kwargs)
