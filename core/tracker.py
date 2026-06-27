"""人脸跟踪: SCRFD 低频检测 + OpenCV 轻跟踪更新中间帧 bbox"""

from __future__ import annotations

import logging

import cv2

from config import DETECT_INTERVAL, OPENCV_TRACKER_TYPE

logger = logging.getLogger(__name__)


class FaceTracker:
    """检测 + IOU 关联 + OpenCV 单目标轻跟踪。

    lost_frames 表示连续几次检测没有匹配到，不代表中间复用缓存的帧数。
    这样人在移动时，旧 track 不会在检测间隔里不断老化并和新 track 一起被返回。
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

    def update(self, frame, recognizer) -> list[dict]:
        self._frame_count += 1
        if self._frame_count % self._detect_interval == 1 or not self._tracks:
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
                "track_id": t["track_id"],
            }
            for t in self._tracks
            if t["lost_frames"] == 0
        ]

    def _associate(self, detections: list[dict], frame) -> None:
        matched_track_ids: set[int] = set()
        for det in detections:
            best_score = 0.0
            best_track: dict | None = None
            det_bbox = det["bbox"]
            for t in self._tracks:
                if t["track_id"] in matched_track_ids:
                    continue
                iou = self._iou(det_bbox, t["bbox"])
                center_score = self._center_score(det_bbox, t["bbox"])
                score = max(iou, center_score)
                if score > best_score and score >= self._iou_threshold:
                    best_score = score
                    best_track = t
            if best_track is not None:
                best_track["bbox"] = det_bbox
                best_track["embedding"] = det["embedding"]
                best_track["det_score"] = det["det_score"]
                best_track["kps"] = det.get("kps")
                best_track["lost_frames"] = 0
                best_track["tracker"] = self._init_cv_tracker(frame, det_bbox)
                matched_track_ids.add(best_track["track_id"])
            else:
                track_id = self._next_track_id
                self._tracks.append(
                    {
                        "track_id": track_id,
                        "bbox": det_bbox,
                        "embedding": det["embedding"],
                        "det_score": det["det_score"],
                        "kps": det.get("kps"),
                        "lost_frames": 0,
                        "tracker": self._init_cv_tracker(frame, det_bbox),
                    }
                )
                matched_track_ids.add(track_id)
                self._next_track_id += 1
        for t in self._tracks:
            if t["track_id"] not in matched_track_ids:
                t["lost_frames"] += 1
        self._prune_lost_tracks()

    def _track_frame(self, frame) -> None:
        h, w = frame.shape[:2]
        for track in self._tracks:
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

            bbox = self._tracker_box_to_bbox(box, w, h)
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
        tracker_box = self._bbox_to_tracker_box(bbox, w, h)
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

    @staticmethod
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

    @staticmethod
    def _tracker_box_to_bbox(box, frame_w: int, frame_h: int) -> list[int] | None:
        x, y, box_w, box_h = box
        x1 = max(0, min(frame_w - 1, int(round(x))))
        y1 = max(0, min(frame_h - 1, int(round(y))))
        x2 = max(0, min(frame_w - 1, int(round(x + box_w))))
        y2 = max(0, min(frame_h - 1, int(round(y + box_h))))
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        return [x1, y1, x2, y2]

    @staticmethod
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

    @staticmethod
    def _center_score(box_a: list[int], box_b: list[int]) -> float:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
        bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
        distance = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
        scale = max(ax2 - ax1, ay2 - ay1, bx2 - bx1, by2 - by1, 1)
        return max(0.0, 1.0 - distance / scale)
