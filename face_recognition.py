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
)

logger = logging.getLogger(__name__)

CHECKIN_FILE = os.path.join(CACHE_DIR, "checkins.json")


class CheckInTracker:
    """每日签到去重: 同一个人同一天只打卡一次, 签退后当天不再打卡"""

    def __init__(self):
        self._records: dict[str, list[str]] = {}  # {"2026-06-23": ["张三", "李四"]}
        self._checked_out: set[str] = set()        # 今日已签退的人
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
            json.dump({
                "records": self._records,
                "checked_out": list(self._checked_out),
            }, f, ensure_ascii=False, indent=2)

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
            self._checked_out = {n for n in self._checked_out if n in self._records.get(today, [])}
        self._save()

    def cleanup(self):
        """清除 7 天前的记录"""
        today = date.today()
        expired = [d for d in self._records
                   if (date.fromisoformat(d) - today).days < -7]
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
            results.append({
                "bbox": bbox,
                "embedding": face.normed_embedding,
                "det_score": float(face.det_score),
            })
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
