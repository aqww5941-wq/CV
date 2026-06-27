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
        if self._app is not None:
            return
        logger.info("正在初始化 InsightFace 模型 (首次运行会下载模型, 请耐心等待)...")
        self._app = FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            providers=INSIGHTFACE_PROVIDERS,
        )
        self._app.prepare(ctx_id=0, det_thresh=DETECTION_THRESHOLD)
        logger.info("模型初始化完成 (providers=%s)", INSIGHTFACE_PROVIDERS)

    @property
    def app(self) -> FaceAnalysis:
        if self._app is None:
            raise RuntimeError("模型未初始化, 请先调用 init_model()")
        return self._app

    def detect(self, frame: np.ndarray) -> list[dict]:
        faces = self.app.get(frame)
        results = []
        for face in faces:
            bbox = face.bbox.astype(int).tolist()
            results.append(
                {
                    "bbox": bbox,
                    "embedding": face.normed_embedding,
                    "det_score": float(face.det_score),
                    "kps": face.kps.astype(float).tolist()
                    if getattr(face, "kps", None) is not None
                    else None,
                }
            )
        return results

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
