"""Per-track recognition cache for known people and remembered visitors."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from config import UNKNOWN_CACHE_EMBEDDING_DELTA, UNKNOWN_CACHE_TTL_SECONDS


@dataclass(frozen=True)
class CachedUnknownVisitor:
    visitor_id: str
    label: str
    similarity: float
    is_returning: bool


@dataclass
class _CacheEntry:
    kind: str
    similarity: float
    embedding: np.ndarray
    updated_at: float
    name: str | None = None
    visitor_id: str | None = None
    label: str | None = None
    is_returning: bool = False


class RecognitionCache:
    """Caches recognition results by track_id.

    Known employees are cached for the lifetime of the track. Unknown visitors are
    cached briefly so the same track does not repeatedly run full database and
    persistent visitor matching while the embedding is effectively unchanged.
    """

    def __init__(self):
        self._cache: dict[int, _CacheEntry] = {}

    def get_known(self, track_id: int) -> tuple[str | None, float | None]:
        entry = self._cache.get(track_id)
        if entry is not None and entry.kind == "known":
            return entry.name, entry.similarity
        return None, None

    def get_known_miss(self, track_id: int, embedding) -> float | None:
        entry = self._cache.get(track_id)
        if entry is None or entry.kind != "known_miss":
            return None
        if time.time() - entry.updated_at > UNKNOWN_CACHE_TTL_SECONDS:
            return None

        current = _normalized(embedding)
        similarity = float(np.dot(entry.embedding, current))
        if 1.0 - similarity > UNKNOWN_CACHE_EMBEDDING_DELTA:
            return None
        return entry.similarity

    def set_known(self, track_id: int, name: str, similarity: float, embedding) -> None:
        self._cache[track_id] = _CacheEntry(
            kind="known",
            name=name,
            similarity=float(similarity),
            embedding=_normalized(embedding),
            updated_at=time.time(),
        )

    def set_known_miss(self, track_id: int, similarity: float, embedding) -> None:
        self._cache[track_id] = _CacheEntry(
            kind="known_miss",
            similarity=float(similarity),
            embedding=_normalized(embedding),
            updated_at=time.time(),
        )

    def get_unknown(self, track_id: int, embedding) -> CachedUnknownVisitor | None:
        entry = self._cache.get(track_id)
        if entry is None or entry.kind != "unknown":
            return None
        current = _normalized(embedding)
        similarity = float(np.dot(entry.embedding, current))
        if 1.0 - similarity > UNKNOWN_CACHE_EMBEDDING_DELTA:
            return None

        return CachedUnknownVisitor(
            visitor_id=entry.visitor_id or "",
            label=entry.label or "未知访客",
            similarity=entry.similarity,
            is_returning=entry.is_returning,
        )

    def set_unknown(
        self,
        track_id: int,
        visitor_id: str,
        label: str,
        similarity: float,
        is_returning: bool,
        embedding,
    ) -> None:
        self._cache[track_id] = _CacheEntry(
            kind="unknown",
            visitor_id=visitor_id,
            label=label,
            similarity=float(similarity),
            is_returning=is_returning,
            embedding=_normalized(embedding),
            updated_at=time.time(),
        )

    def cleanup(self, active_track_ids: set[int]) -> None:
        for tid in list(self._cache.keys()):
            if tid not in active_track_ids:
                self._cache.pop(tid, None)

    def __len__(self) -> int:
        return len(self._cache)


def _normalized(embedding) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector
