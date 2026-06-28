"""人脸特征库管理: 扫描员工照片 -> 提取特征 -> 缓存为 pickle"""

from __future__ import annotations

import logging
import os
import pickle

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from config import (
    EMPLOYEES_DIR,
    CACHE_FILE,
)
from core.insightface_factory import create_face_analysis

logger = logging.getLogger(__name__)
CACHE_VERSION = 2


class FaceDatabase:
    """本地人脸特征库"""

    def __init__(self, app: FaceAnalysis | None = None):
        self.embeddings: list[tuple[str, np.ndarray]] = []
        self._app = app

    def _get_app(self) -> FaceAnalysis:
        if self._app is None:
            logger.info("正在初始化 InsightFace 模型用于构建人脸库...")
            self._app = create_face_analysis()
        return self._app

    def build(self, force: bool = False) -> None:
        if os.path.exists(CACHE_FILE) and not force:
            logger.info("发现缓存文件, 直接加载...")
            if self.load_cache():
                return
            logger.info("人脸库缓存格式过旧, 将重建为多向量底库...")
        logger.info("开始扫描员工照片目录...")
        app = self._get_app()
        self.embeddings = []
        if not os.path.exists(EMPLOYEES_DIR):
            logger.warning("employees 目录不存在, 人脸库为空")
            return
        for employee_name in sorted(os.listdir(EMPLOYEES_DIR)):
            employee_dir = os.path.join(EMPLOYEES_DIR, employee_name)
            if not os.path.isdir(employee_dir):
                continue
            embeddings_for_person = []
            for filename in sorted(os.listdir(employee_dir)):
                if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                    continue
                img_path = os.path.join(employee_dir, filename)
                emb = self._extract_embedding(app, img_path)
                if emb is not None:
                    embeddings_for_person.append(emb)
                    self.embeddings.append((employee_name, emb))
                    logger.info("  提取特征: %s / %s", employee_name, filename)
            if embeddings_for_person:
                logger.info(
                    "-> %s: 保留 %d 枚照片特征, 特征维度 %d",
                    employee_name,
                    len(embeddings_for_person),
                    embeddings_for_person[0].shape[0],
                )
        logger.info(
            "人脸库建立完成, 共 %d 人 / %d 枚向量",
            len({name for name, _ in self.embeddings}),
            len(self.embeddings),
        )
        self._save_cache()

    def _extract_embedding(self, app: FaceAnalysis, img_path: str) -> np.ndarray | None:
        img = cv2.imread(img_path)
        if img is None:
            logger.warning("无法读取图片: %s", img_path)
            return None
        faces = app.get(img)
        if len(faces) == 0:
            logger.warning("未检测到人脸: %s", img_path)
            return None
        return faces[0].normed_embedding

    def _save_cache(self) -> None:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(
                {"version": CACHE_VERSION, "embeddings": self.embeddings},
                f,
            )
        logger.info("人脸库已缓存到: %s", CACHE_FILE)

    def load_cache(self) -> bool:
        with open(CACHE_FILE, "rb") as f:
            payload = pickle.load(f)
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return False
        self.embeddings = payload.get("embeddings", [])
        logger.info(
            "从缓存加载人脸库成功, 共 %d 人 / %d 枚向量",
            len({name for name, _ in self.embeddings}),
            len(self.embeddings),
        )
        return True

    def get_all(self) -> list[tuple[str, np.ndarray]]:
        return self.embeddings

    def __len__(self) -> int:
        return len(self.embeddings)
