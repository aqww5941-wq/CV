"""Run Doubao realtime voice dialog without starting face recognition."""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.realtime_dialog import RealtimeDialogService


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    service = RealtimeDialogService()
    if not service.start():
        return 1

    stopping = False

    def stop(_sig, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print("实时语音已启动，按 Ctrl+C 退出。")
    try:
        while not stopping:
            time.sleep(0.5)
    finally:
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
