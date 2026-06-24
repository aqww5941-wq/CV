"""人脸跟踪: SCRFD 检测 + IOU 匹配, 每 N 帧检测一次, 中间帧复用缓存"""

from __future__ import annotations

from config import DETECT_INTERVAL


class FaceTracker:
    """检测 + IOU 跟踪: 每 N 帧做一次 SCRFD 检测, 中间帧复用缓存, 大幅降低 CPU 占用。"""

    def __init__(
        self,
        detect_interval: int = DETECT_INTERVAL,
        iou_threshold: float = 0.3,
        max_lost_frames: int = 30,
    ):
        self._detect_interval = detect_interval
        self._iou_threshold = iou_threshold
        self._max_lost_frames = max_lost_frames
        self._frame_count = 0
        self._next_track_id = 1
        self._tracks: list[dict] = []

    def update(self, frame, recognizer) -> list[dict]:
        self._frame_count += 1
        if self._frame_count % self._detect_interval == 1 or not self._tracks:
            detections = recognizer.detect(frame)
            self._associate(detections)
        else:
            self._age_tracks()
        return [
            {
                "bbox": t["bbox"],
                "embedding": t["embedding"],
                "det_score": t["det_score"],
                "track_id": t["track_id"],
            }
            for t in self._tracks
        ]

    def _associate(self, detections: list[dict]) -> None:
        matched_track_ids: set[int] = set()
        for det in detections:
            best_iou = 0.0
            best_track: dict | None = None
            det_bbox = det["bbox"]
            for t in self._tracks:
                if t["track_id"] in matched_track_ids:
                    continue
                iou = self._iou(det_bbox, t["bbox"])
                if iou > best_iou and iou >= self._iou_threshold:
                    best_iou = iou
                    best_track = t
            if best_track is not None:
                best_track["bbox"] = det_bbox
                best_track["embedding"] = det["embedding"]
                best_track["det_score"] = det["det_score"]
                best_track["lost_frames"] = 0
                matched_track_ids.add(best_track["track_id"])
            else:
                self._tracks.append(
                    {
                        "track_id": self._next_track_id,
                        "bbox": det_bbox,
                        "embedding": det["embedding"],
                        "det_score": det["det_score"],
                        "lost_frames": 0,
                    }
                )
                self._next_track_id += 1
        for t in self._tracks:
            if t["track_id"] not in matched_track_ids:
                t["lost_frames"] += 1
        self._prune_lost_tracks()

    def _age_tracks(self) -> None:
        for t in self._tracks:
            t["lost_frames"] += 1
        self._prune_lost_tracks()

    def _prune_lost_tracks(self) -> None:
        self._tracks = [
            t for t in self._tracks if t["lost_frames"] <= self._max_lost_frames
        ]
        if not self._tracks:
            self._next_track_id = 1

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
