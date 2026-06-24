"""特征缓存: track_id → 已识别身份, 避免同一 track 重复跑 ArcFace 匹配"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class RecognitionCache:
    """同一 track_id 首次匹配成功后缓存结果, 后续帧直接读缓存, 不再跑全库余弦比对。

    用法:
        cache = RecognitionCache()
        name, sim = cache.get(track_id)
        if name is None:
            name, sim = recognizer.match(embedding, db_embeddings)
            if name is not None:
                cache.set(track_id, name, sim)
    """

    def __init__(self):
        self._cache: dict[int, tuple[str, float]] = {}

    def get(self, track_id: int) -> tuple[str | None, float | None]:
        entry = self._cache.get(track_id)
        if entry is not None:
            return entry[0], entry[1]
        return None, None

    def set(self, track_id: int, name: str, similarity: float) -> None:
        self._cache[track_id] = (name, similarity)

    def cleanup(self, active_track_ids: set[int]) -> None:
        for tid in list(self._cache.keys()):
            if tid not in active_track_ids:
                self._cache.pop(tid, None)

    def __len__(self) -> int:
        return len(self._cache)
