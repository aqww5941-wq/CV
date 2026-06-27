"""Persistent memory for visitors who are not enrolled employees."""

from __future__ import annotations

import os
import pickle
import time
from dataclasses import dataclass

import numpy as np

from config import (
    UNKNOWN_VISITOR_MATCH_THRESHOLD,
    UNKNOWN_VISITOR_UPDATE_COOLDOWN_SECONDS,
    UNKNOWN_VISITORS_FILE,
)


@dataclass(frozen=True)
class UnknownVisitorMatch:
    visitor_id: str
    label: str
    similarity: float
    is_returning: bool
    visit_count: int


class UnknownVisitorStore:
    """Stores normalized embeddings for unknown visitors across app restarts."""

    def __init__(self, path: str = UNKNOWN_VISITORS_FILE):
        self.path = path
        self._records: dict[str, dict] = {}
        self._load()

    def match_or_create(self, embedding) -> UnknownVisitorMatch:
        vector = _normalized(embedding)
        now = time.time()
        visitor_id, similarity = self._best_match(vector)
        if visitor_id is not None and similarity >= UNKNOWN_VISITOR_MATCH_THRESHOLD:
            record = self._records[visitor_id]
            is_returning = True
            if now - float(record.get("last_seen", 0.0)) >= UNKNOWN_VISITOR_UPDATE_COOLDOWN_SECONDS:
                record["visit_count"] = int(record.get("visit_count", 1)) + 1
                record["embedding"] = _normalized(
                    (np.asarray(record["embedding"], dtype=np.float32) + vector) / 2.0
                )
            record["last_seen"] = now
            self._save()
            return UnknownVisitorMatch(
                visitor_id=visitor_id,
                label=record["label"],
                similarity=similarity,
                is_returning=is_returning,
                visit_count=int(record.get("visit_count", 1)),
            )

        visitor_id = self._next_id()
        label = f"访客{int(visitor_id):03d}"
        self._records[visitor_id] = {
            "label": label,
            "embedding": vector,
            "first_seen": now,
            "last_seen": now,
            "visit_count": 1,
        }
        self._save()
        return UnknownVisitorMatch(
            visitor_id=visitor_id,
            label=label,
            similarity=0.0,
            is_returning=False,
            visit_count=1,
        )

    def _best_match(self, vector: np.ndarray) -> tuple[str | None, float]:
        best_id = None
        best_similarity = 0.0
        for visitor_id, record in self._records.items():
            stored = _normalized(record["embedding"])
            similarity = float(np.dot(stored, vector))
            if similarity > best_similarity:
                best_id = visitor_id
                best_similarity = similarity
        return best_id, best_similarity

    def _next_id(self) -> str:
        if not self._records:
            return "1"
        return str(max(int(visitor_id) for visitor_id in self._records) + 1)

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, "rb") as f:
            self._records = pickle.load(f)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "wb") as f:
            pickle.dump(self._records, f)

    def __len__(self) -> int:
        return len(self._records)


def _normalized(embedding) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector
