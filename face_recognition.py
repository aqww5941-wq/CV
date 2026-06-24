"""实时人脸识别引擎: 检测 + 特征提取 + 匹配 + 每日签到去重"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import date

import numpy as np
import cv2
from insightface.app import FaceAnalysis

from config import (
    CACHE_DIR,
    INSIGHTFACE_MODEL,
    DETECTION_THRESHOLD,
    MATCH_THRESHOLD,
    DEBOUNCE_SECONDS,
    DETECT_INTERVAL,
)

logger = logging.getLogger(__name__)

CHECKIN_FILE = os.path.join(CACHE_DIR, "checkins.json")


class CheckInTracker:
    """每日签到去重: 同一个人同一天只打卡一次, 签退后当天不再打卡"""

    def __init__(self):
        self._records: dict[str, list[str]] = {}  # {"2026-06-23": ["张三", "李四"]}
        self._checked_out: set[str] = set()  # 今日已签退的人
        self._load()

    def _load(self):
        if os.path.exists(CHECKIN_FILE):
            with open(CHECKIN_FILE, "r") as f:
                data = json.load(f)
                if "records" in data:
                    self._records = data["records"]
                    self._checked_out = set(data.get("checked_out", []))
                else:
                    # 旧格式兼容: {"2026-06-23": ["张三"]} → 迁移为新格式
                    self._records = data
                    self._checked_out = set()

    def _save(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CHECKIN_FILE, "w") as f:
            json.dump(
                {
                    "records": self._records,
                    "checked_out": list(self._checked_out),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def is_checked_in_today(self, name: str) -> bool:
        """检查某人今天是否已打卡或已签退"""
        today = date.today().isoformat()
        return name in self._records.get(today, [])

    def is_checked_out_today(self, name: str) -> bool:
        """检查某人今天是否已签退"""
        return name in self._checked_out

    def mark_checked_in(self, name: str):
        """标记某人今天已打卡"""
        today = date.today().isoformat()
        if today not in self._records:
            self._records[today] = []
        if name not in self._records[today]:
            self._records[today].append(name)
            self._save()

    def reset_checkin(self, name: str):
        """下班打卡: 标记已签退, 当天不再允许重新打卡"""
        self._checked_out.add(name)
        # 清理旧日期的 checked_out
        today = date.today().isoformat()
        if today in self._records:
            self._checked_out = {
                n for n in self._checked_out if n in self._records.get(today, [])
            }
        self._save()

    def cleanup(self):
        """清除 7 天前的记录"""
        today = date.today()
        expired = [
            d for d in self._records if (date.fromisoformat(d) - today).days < -7
        ]
        for d in expired:
            del self._records[d]
        self._checked_out = set()
        self._save()


class FaceRecognizer:
    """实时人脸识别器"""

    def __init__(self):
        self._app: FaceAnalysis | None = None
        # 防抖记录: {name: last_welcome_timestamp}
        self._last_welcome: dict[str, float] = defaultdict(float)
        # 陌生人防抖记录
        self._last_stranger_log: float = 0.0

    def init_model(self) -> None:
        """初始化 InsightFace 模型 (首次调用时自动下载模型文件)"""
        logger.info("正在初始化 InsightFace 模型 (首次运行会下载模型, 请耐心等待)...")
        self._app = FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            providers=["CPUExecutionProvider"],
        )
        self._app.prepare(ctx_id=-1, det_thresh=DETECTION_THRESHOLD)
        logger.info("模型初始化完成")

    def detect(self, frame: np.ndarray) -> list[dict]:
        """
        检测帧中的所有人脸, 返回:
        [
          {
            "bbox": [x1, y1, x2, y2],
            "embedding": np.ndarray,  # 归一化特征向量
            "det_score": float,
          },
          ...
        ]
        """
        if self._app is None:
            raise RuntimeError("模型未初始化, 请先调用 init_model()")

        faces = self._app.get(frame)

        results = []
        for face in faces:
            bbox = face.bbox.astype(int).tolist()
            results.append(
                {
                    "bbox": bbox,
                    "embedding": face.normed_embedding,
                    "det_score": float(face.det_score),
                }
            )
        return results

    def match(
        self,
        embedding: np.ndarray,
        face_db_embeddings: list[tuple[str, np.ndarray]],
    ) -> tuple[str | None, float]:
        """
        将一个人脸特征与库中所有人脸做余弦相似度匹配。
        返回 (姓名或None, 最高相似度)
        """
        if not face_db_embeddings:
            return None, 0.0

        best_name = None
        best_similarity = 0.0

        for name, db_embedding in face_db_embeddings:
            sim = self._cosine_similarity(embedding, db_embedding)
            if sim > best_similarity:
                best_similarity = sim
                best_name = name

        if best_similarity < MATCH_THRESHOLD:
            return None, best_similarity

        return best_name, best_similarity

    def should_welcome(self, name: str) -> bool:
        """
        防抖检查: 同一个人在 DEBOUNCE_SECONDS 内只欢迎一次。
        """
        now = time.time()
        last = self._last_welcome.get(name, 0)
        if now - last >= DEBOUNCE_SECONDS:
            self._last_welcome[name] = now
            return True
        return False

    def should_log_stranger(self) -> bool:
        """
        陌生人防抖: DEBOUNCE_SECONDS 内只输出一次陌生人日志。
        """
        now = time.time()
        if now - self._last_stranger_log >= DEBOUNCE_SECONDS:
            self._last_stranger_log = now
            return True
        return False

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """余弦相似度 (向量已归一化, 直接点积即可)"""
        return float(np.dot(a, b))


class FaceTracker:
    """检测 + IOU 跟踪: 每 N 帧做一次 SCRFD 检测, 中间帧复用缓存, 大幅降低 CPU 占用。

    数据流:
        第 1 帧  → detect() → 分配 track_id → 缓存
        第 2~14 帧 → 跳过检测, 返回缓存
        第 15 帧 → detect() → IOU 匹配 → 更新 track_id → 缓存
        ...
    """

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
        self._tracks: list[
            dict
        ] = []  # 活跃轨迹: [{track_id, bbox, embedding, det_score, lost_frames}]

    def update(self, frame: np.ndarray, recognizer: FaceRecognizer) -> list[dict]:
        """每帧调用, 返回当前帧的人脸列表 (格式同 FaceRecognizer.detect + track_id)。"""
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
        """IOU 匹配: 将新检测结果与已有轨迹关联, 无匹配的轨迹标记 lost, 新检测分配新 ID。"""
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
        """非检测帧: 所有轨迹 lost_frames +1, 超出阈值则移除。"""
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
        """计算两个 bbox 的 IoU (Intersection over Union)。"""
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
