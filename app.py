"""AI 智慧前台数字人系统 - 模块化工程版"""

import logging
import sys
import time

import cv2

from core.async_pipeline import AsyncPipelineWrapper
from config import (
    CAMERA_INDEX,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    CAMERA_BUFFER_SIZE,
    ENABLE_GUI,
    DETECT_INTERVAL,
    VOTE_WINDOW,
)
from core.attendance_db import AttendanceDB
from core.events import EventBus
from core.face_db import FaceDatabase
from core.recognizer import FaceRecognizer
from core.recognition_cache import RecognitionCache
from core.recognition_pipeline import RecognitionPipeline
from core.redis_checkin import RedisCheckIn
from core.tracker import FaceTracker
from core.unknown_visitors import UnknownVisitorStore
from core.vector_db import VectorDB
from core.vote import VoteBuffer
from core.voice_system import VoiceSystem
from ui.gui import OpenCVGuiLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")


def _run_headless_loop(
    cap,
    pipeline,
    checkin_tracker,
):
    logger.info(
        "无界面模式启动 (ENABLE_GUI=False)，检测间隔=%d 帧，投票窗口=%d/%d 票，摄像头静默运行中...",
        DETECT_INTERVAL,
        VOTE_WINDOW,
        VOTE_WINDOW,
    )
    logger.info("按 Ctrl+C 退出")
    fps_start = time.time()
    fps_frames = 0

    async_pipeline = AsyncPipelineWrapper(pipeline)
    async_pipeline.start()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            async_pipeline.submit_frame(frame)
            now = time.time()

            fps_frames += 1
            if now - fps_start >= 10.0:
                fps_display = f"{fps_frames / 10:.1f}"
                logger.debug(
                    "FPS: %s, 今日已签: %d 人",
                    fps_display,
                    checkin_tracker.get_today_count(),
                )
                fps_frames = 0
                fps_start = now

    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        async_pipeline.stop()
        cap.release()


def _embedding_person_count(embeddings) -> int:
    return len({name for name, _ in embeddings})


def main():
    logger.info("=" * 50)
    logger.info("AI 智慧前台数字人系统 (MVP Optimized)")
    logger.info("=" * 50)

    recognizer = FaceRecognizer()
    recognizer.init_model()

    face_db = FaceDatabase(app=recognizer.app)
    face_db.build()
    db_embeddings = face_db.get_all()

    vector_db = None
    try:
        vector_db = VectorDB()
        if len(vector_db) > 0:
            pg_embeddings = vector_db.get_all_embeddings()
            logger.info(
                "pgvector 底库: %d 人 / %d 枚向量",
                _embedding_person_count(pg_embeddings),
                len(pg_embeddings),
            )
            pg_names = {name for name, _ in pg_embeddings}
            db_embeddings = [
                (name, emb) for name, emb in db_embeddings if name not in pg_names
            ]
            db_embeddings.extend(pg_embeddings)
            logger.info(
                "合并后底库: %d 人 / %d 枚向量",
                _embedding_person_count(db_embeddings),
                len(db_embeddings),
            )
        else:
            logger.info(
                "pgvector 为空, 使用 pickle 缓存底库: %d 人 / %d 枚向量",
                _embedding_person_count(db_embeddings),
                len(db_embeddings),
            )
    except Exception as e:
        logger.warning("pgvector 不可用, 降级为 pickle 缓存: %s", e)

    tracker = FaceTracker(detect_interval=DETECT_INTERVAL)

    attendance_db = AttendanceDB()
    checkin_tracker = RedisCheckIn()
    logger.info("签到去重: Redis")

    vote_buffer = VoteBuffer()
    rec_cache = RecognitionCache()
    unknown_visitors = UnknownVisitorStore()
    logger.info("未知访客记忆库: %d 人", len(unknown_visitors))

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        logger.error("无法打开摄像头!")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_BUFFER_SIZE)

    voice_system = VoiceSystem()
    voice_system.start()
    event_bus = EventBus(emotion_module=voice_system.emotion)
    pipeline = RecognitionPipeline(
        recognizer=recognizer,
        tracker=tracker,
        db_embeddings=db_embeddings,
        attendance_db=attendance_db,
        checkin_tracker=checkin_tracker,
        vote_buffer=vote_buffer,
        rec_cache=rec_cache,
        event_bus=event_bus,
        unknown_visitors=unknown_visitors,
    )

    try:
        if ENABLE_GUI:
            OpenCVGuiLoop(
                cap,
                face_db,
                db_embeddings,
                pipeline,
                checkin_tracker,
            ).run()
        else:
            _run_headless_loop(
                cap,
                pipeline,
                checkin_tracker,
            )
    finally:
        pipeline.shutdown()
        voice_system.stop()


if __name__ == "__main__":
    main()
