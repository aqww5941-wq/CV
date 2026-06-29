"""多帧投票: 连续 N 帧识别结果投票, 避免单帧误识别 (眨眼/侧脸/模糊/运动)"""

from __future__ import annotations

from collections import defaultdict, deque

from config import VOTE_WINDOW, VOTE_MIN_VOTES


class VoteBuffer:
    """多帧投票缓冲区。

    用法:
        buf = VoteBuffer(window=5, min_votes=3)
        voted_name = buf.vote(track_id, name, similarity, time.time())
        if voted_name is not None:
            check_in(voted_name)
    """

    def __init__(
        self,
        window: int = VOTE_WINDOW,
        min_votes: int = VOTE_MIN_VOTES,
        cooldown: float = 5.0,
    ):
        self._window = window
        self._min_votes = min_votes
        self._cooldown = cooldown
        self._buffers: dict[int, deque[tuple[str, float]]] = defaultdict(
            lambda: deque(maxlen=window)
        )
        self._confirmed: dict[int, tuple[str, float]] = {}

    def vote(
        self, track_id: int, name: str | None, similarity: float, now: float
    ) -> str | None:
        if track_id in self._confirmed:
            confirmed_name, confirmed_time = self._confirmed[track_id]
            if now - confirmed_time < self._cooldown:
                return None
        key = "__UNKNOWN__" if name is None else name
        self._buffers[track_id].append((key, similarity))
        buf = self._buffers[track_id]
        if len(buf) < self._min_votes:
            return None
        counts: dict[str, int] = defaultdict(int)
        for n, _ in buf:
            if n != "__UNKNOWN__":
                counts[n] += 1
        if not counts:
            return None
        if key != "__UNKNOWN__" and counts[key] >= self._min_votes:
            self._confirmed[track_id] = (key, now)
            return key
        return None

    def cleanup_inactive(self, active_track_ids: set[int]) -> None:
        for tid in list(self._buffers.keys()):
            if tid not in active_track_ids:
                self._buffers.pop(tid, None)
                self._confirmed.pop(tid, None)
