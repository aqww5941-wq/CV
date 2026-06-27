"""Vectorized in-memory face embedding matcher."""

from __future__ import annotations

import numpy as np

from config import MATCH_THRESHOLD


class EmbeddingMatcher:
    """Matches one embedding against a prebuilt normalized embedding matrix."""

    def __init__(self, embeddings: list[tuple[str, np.ndarray]] | None = None):
        self.names: list[str] = []
        self.matrix = np.empty((0, 0), dtype=np.float32)
        if embeddings is not None:
            self.update(embeddings)

    def update(self, embeddings: list[tuple[str, np.ndarray]]) -> None:
        self.names = [name for name, _ in embeddings]
        if not embeddings:
            self.matrix = np.empty((0, 0), dtype=np.float32)
            return

        matrix = np.asarray([embedding for _, embedding in embeddings], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.matrix = matrix / norms

    def match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        if self.matrix.size == 0:
            return None, 0.0

        vector = np.asarray(embedding, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        scores = self.matrix @ vector
        best_idx = int(np.argmax(scores))
        best_similarity = float(scores[best_idx])
        if best_similarity < MATCH_THRESHOLD:
            return None, best_similarity
        return self.names[best_idx], best_similarity

    def __len__(self) -> int:
        return len(self.names)

