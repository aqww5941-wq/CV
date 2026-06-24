"""实时人脸识别引擎: InsightFace 检测 + 特征提取 + 余弦相似度匹配"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

import numpy as np
from insightface.app import FaceAnalysis

from config import (
    INSIGHTFACE_MODEL,
    DETECTION_THRESHOLD,
    MATCH_THRESHOLD,
    DEBOUNCE_SECONDS,
    INSIGHTFACE_PROVIDERS,
)

logger = logging.getLogger(__name__)


class FaceRecognizer:
    """实时人脸识别器"""

    def __init__(self):
        self._app: FaceAnalysis | None = None
        self._last_welcome: dict[str, float] = defaultdict(float)
        self._last_stranger_log: float = 0.0

    def init_model(self) -> None:
        logger.info("正在初始化 InsightFace 模型 (首次运行会下载模型, 请耐心等待)...")
        self._app = FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            providers=INSIGHTFACE_PROVIDERS,
        )
        self._app.prepare(ctx_id=0, det_thresh=DETECTION_THRESHOLD)
        logger.info("模型初始化完成 (providers=%s)", INSIGHTFACE_PROVIDERS)

    def detect(self, frame: np.ndarray) -> list[dict]:
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
        self, embedding: np.ndarray, face_db_embeddings: list[tuple[str, np.ndarray]]
    ) -> tuple[str | None, float]:
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
        now = time.time()
        last = self._last_welcome.get(name, 0)
        if now - last >= DEBOUNCE_SECONDS:
            self._last_welcome[name] = now
            return True
        return False

    def should_log_stranger(self) -> bool:
        now = time.time()
        if now - self._last_stranger_log >= DEBOUNCE_SECONDS:
            self._last_stranger_log = now
            return True
        return False

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))
