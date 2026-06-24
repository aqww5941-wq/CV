"""人脸特征库管理: 扫描员工照片 -> 提取特征 -> 缓存为 pickle"""

import os
import pickle
import logging

import numpy as np
import cv2
from insightface.app import FaceAnalysis

from config import EMPLOYEES_DIR, CACHE_FILE, INSIGHTFACE_MODEL, DETECTION_THRESHOLD

logger = logging.getLogger(__name__)


class FaceDatabase:
    """本地人脸特征库"""

    def __init__(self):
        self.embeddings: list[tuple[str, np.ndarray]] = []
        self._app = None

    def _get_app(self) -> FaceAnalysis:
        """延迟初始化 InsightFace (只加载一次)"""
        if self._app is None:
            self._app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
            self._app.prepare(ctx_id=-1, det_thresh=DETECTION_THRESHOLD)
        return self._app

    def build(self, force: bool = False) -> None:
        """
        从 employees 目录建立人脸库。
        如果缓存存在且 force=False, 直接加载缓存。
        """
        if os.path.exists(CACHE_FILE) and not force:
            logger.info("发现缓存文件, 直接加载...")
            self.load_cache()
            return

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
                    logger.info("  提取特征: %s / %s", employee_name, filename)

            if embeddings_for_person:
                # 取该员工所有照片特征向量的均值作为最终特征
                avg_embedding = np.mean(embeddings_for_person, axis=0)
                # L2 归一化
                avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
                self.embeddings.append((employee_name, avg_embedding))
                logger.info("-> %s: 使用 %d 张照片, 特征维度 %d",
                            employee_name, len(embeddings_for_person), avg_embedding.shape[0])

        logger.info("人脸库建立完成, 共 %d 人", len(self.embeddings))
        self._save_cache()

    def _extract_embedding(self, app: FaceAnalysis, img_path: str) -> np.ndarray | None:
        """从单张图片提取人脸特征向量。返回 None 表示未检测到人脸。"""
        img = cv2.imread(img_path)
        if img is None:
            logger.warning("无法读取图片: %s", img_path)
            return None

        faces = app.get(img)
        if len(faces) == 0:
            logger.warning("未检测到人脸: %s", img_path)
            return None

        # 取检测到的第一张人脸
        embedding = faces[0].normed_embedding
        return embedding

    def _save_cache(self) -> None:
        """将特征库缓存到 pickle 文件"""
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(self.embeddings, f)
        logger.info("人脸库已缓存到: %s", CACHE_FILE)

    def load_cache(self) -> None:
        """从 pickle 缓存加载特征库"""
        with open(CACHE_FILE, "rb") as f:
            self.embeddings = pickle.load(f)
        logger.info("从缓存加载人脸库成功, 共 %d 人", len(self.embeddings))

    def get_all(self) -> list[tuple[str, np.ndarray]]:
        """返回所有人脸特征: [(姓名, 归一化向量), ...]"""
        return self.embeddings

    def __len__(self) -> int:
        return len(self.embeddings)
