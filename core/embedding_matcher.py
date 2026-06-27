"""Vectorized in-memory face embedding matcher."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

import numpy as np

from config import MATCH_ACCEPT_THRESHOLD, MATCH_PERSON_TOP_K, MATCH_REVIEW_THRESHOLD


@dataclass(frozen=True)
class MatchCandidate:
    name: str | None
    similarity: float
    decision: str


class EmbeddingMatcher:
    """Matches one embedding against a prebuilt normalized embedding matrix.

    Multiple embeddings may share the same name. Matching aggregates each
    person's top-k vector scores so different photo angles can help without
    collapsing the person's identity into one lossy average vector.
    """

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

    def match_candidate(self, embedding: np.ndarray) -> MatchCandidate:
        name, similarity = self._best_person(embedding)
        if name is None:
            return MatchCandidate(None, similarity, "reject")
        if similarity >= MATCH_ACCEPT_THRESHOLD:
            return MatchCandidate(name, similarity, "accept")
        if similarity >= MATCH_REVIEW_THRESHOLD:
            return MatchCandidate(name, similarity, "review")
        return MatchCandidate(None, similarity, "reject")

    def match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        candidate = self.match_candidate(embedding)
        if candidate.decision != "accept":
            return None, candidate.similarity
        return candidate.name, candidate.similarity

    def _best_person(self, embedding: np.ndarray) -> tuple[str | None, float]:
        if self.matrix.size == 0:
            return None, 0.0

        vector = np.asarray(embedding, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        scores = self.matrix @ vector
        per_person_scores: dict[str, list[float]] = defaultdict(list)
        for name, score in zip(self.names, scores):
            per_person_scores[name].append(float(score))

        best_name = None
        best_similarity = 0.0
        top_k = max(1, MATCH_PERSON_TOP_K)
        for name, person_scores in per_person_scores.items():
            top_scores = sorted(person_scores, reverse=True)[:top_k]
            similarity = float(np.mean(top_scores))
            if best_name is None or similarity > best_similarity:
                best_name = name
                best_similarity = similarity
        return best_name, best_similarity

    def __len__(self) -> int:
        return len(self.names)
