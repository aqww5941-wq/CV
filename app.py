"""AI 智慧前台数字人系统 - 模块化工程版"""

import logging
import sys
import time
from datetime import datetime

import cv2
import numpy as np

from config import (
    CAMERA_INDEX,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    MATCH_THRESHOLD,
    ENABLE_CAMERA,
    ALLOW_REPEAT_CHECKIN,
    DETECT_INTERVAL,
    VOTE_WINDOW,
)
from core.attendance_db import AttendanceDB
from core.checkin import CheckInTracker
from core.events import EventBus
from core.face_db import FaceDatabase
from core.recognizer import FaceRecognizer
from core.recognition_cache import RecognitionCache
from core.redis_checkin import RedisCheckIn
from core.sound import play_welcome
from core.tracker import FaceTracker
from core.vector_db import VectorDB
from core.vote import VoteBuffer
from ui.render import (
    COLOR_CYAN,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_DARK_BAR,
    draw_tech_bounding_box,
    draw_rounded_rectangle,
    draw_texts_on_frame,
    text_bbox,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

button_rect = [0, 0, 0, 0]
button_clicked = False
last_recognized_name = ""
last_recognized_bbox = []


def mouse_callback(event, x, y, flags, param):
    global button_clicked
    if event == cv2.EVENT_LBUTTONDOWN:
        bx1, by1, bx2, by2 = button_rect
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            button_clicked = True


def _run_headless_loop(
    cap,
    face_db,
    db_embeddings,
    recognizer,
    tracker,
    attendance_db,
    checkin_tracker,
    vote_buffer,
    rec_cache,
    event_bus,
):
    logger.info(
        "无界面模式启动 (ENABLE_CAMERA=False)，检测间隔=%d 帧，投票窗口=%d/%d 票，摄像头静默运行中...",
        DETECT_INTERVAL,
        VOTE_WINDOW,
        VOTE_WINDOW,
    )
    logger.info("按 Ctrl+C 退出")
    fps_start = time.time()
    fps_frames = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            faces = tracker.update(frame, recognizer)
            active_ids = {face["track_id"] for face in faces}
            vote_buffer.cleanup_inactive(active_ids)
            rec_cache.cleanup(active_ids)

            for face in faces:
                embedding = face["embedding"]
                track_id = face["track_id"]

                name, similarity = rec_cache.get(track_id)
                if name is None:
                    name, similarity = recognizer.match(embedding, db_embeddings)
                    if name is not None:
                        rec_cache.set(track_id, name, similarity)

                voted_name = vote_buffer.vote(track_id, name, similarity, time.time())

                if voted_name is None:
                    if name is None and recognizer.should_log_stranger():
                        logger.info("检测到未知访客")
                    continue

                if not ALLOW_REPEAT_CHECKIN:
                    if checkin_tracker.is_checked_out_today(voted_name):
                        continue
                    if checkin_tracker.is_checked_in_today(voted_name):
                        continue
                    if not checkin_tracker.can_checkin(voted_name, time.time()):
                        continue

                row_id = attendance_db.check_in(voted_name)
                checkin_tracker.mark_checked_in(voted_name)
                event_bus.checkin(voted_name, row_id, similarity)
                play_welcome()
                logger.info(
                    "签到成功: %s (sim=%.3f, row=%s)",
                    voted_name,
                    similarity,
                    row_id,
                )

            fps_frames += 1
            if time.time() - fps_start >= 10.0:
                fps_display = f"{fps_frames / 10:.1f}"
                logger.debug(
                    "FPS: %s, 今日已签: %d 人",
                    fps_display,
                    checkin_tracker.get_today_count(),
                )
                fps_frames = 0
                fps_start = time.time()

    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        cap.release()


def _run_gui_loop(
    cap,
    face_db,
    db_embeddings,
    recognizer,
    tracker,
    attendance_db,
    checkin_tracker,
    vote_buffer,
    rec_cache,
    event_bus,
):
    global button_clicked, last_recognized_name, last_recognized_bbox, button_rect

    win_name = "AI智慧前台数字人系统"
    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(win_name, mouse_callback)

    welcome_text: str = ""
    welcome_until: float = 0.0
    toast_text: str = ""
    toast_until: float = 0.0

    fps_start = time.time()
    fps_frames = 0
    fps_display = ""

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            faces = tracker.update(frame, recognizer)
            h, w = frame.shape[:2]

            last_recognized_name = ""
            text_draws: list[dict] = []

            overlay_bar = frame.copy()
            cv2.rectangle(overlay_bar, (0, 0), (w, 55), COLOR_DARK_BAR, -1)
            cv2.addWeighted(overlay_bar, 0.4, frame, 0.6, 0, frame)
            cv2.line(frame, (0, 55), (w, 55), COLOR_CYAN, 1, lineType=cv2.LINE_AA)

            active_ids = {face["track_id"] for face in faces}
            vote_buffer.cleanup_inactive(active_ids)
            rec_cache.cleanup(active_ids)

            for face in faces:
                bbox = face["bbox"]
                embedding = face["embedding"]
                track_id = face["track_id"]

                name, similarity = rec_cache.get(track_id)
                if name is None:
                    name, similarity = recognizer.match(embedding, db_embeddings)
                    if name is not None:
                        rec_cache.set(track_id, name, similarity)
                recognized = name is not None

                x1, y1, x2, y2 = bbox
                color = COLOR_GREEN if recognized else COLOR_RED

                draw_tech_bounding_box(frame, bbox, color, thickness=3, length=18)

                if recognized:
                    last_recognized_name = name
                    last_recognized_bbox = bbox

                    if (
                        not ALLOW_REPEAT_CHECKIN
                        and checkin_tracker.is_checked_out_today(name)
                    ):
                        label = f"已签退 · {name}"
                    elif (
                        not ALLOW_REPEAT_CHECKIN
                        and checkin_tracker.is_checked_in_today(name)
                    ):
                        label = f"已签到 · {name}"
                    else:
                        label = name
                        voted_name = vote_buffer.vote(
                            track_id, name, similarity, time.time()
                        )
                        if voted_name is not None:
                            if (
                                not ALLOW_REPEAT_CHECKIN
                                and not checkin_tracker.can_checkin(
                                    voted_name, time.time()
                                )
                            ):
                                pass
                            else:
                                row_id = attendance_db.check_in(voted_name)
                                checkin_tracker.mark_checked_in(voted_name)
                                event_bus.checkin(voted_name, row_id, similarity)
                                play_welcome()
                                welcome_text = f"欢迎回来, {voted_name}! 签到成功"
                                welcome_until = time.time() + 3.0
                                label = f"已签到 · {voted_name}"
                else:
                    label = "未知访客"

                _, _, tw, th = text_bbox(label, 16)
                pad_x, pad_y = 10, 6
                lbl_x1 = max(0, x1)
                lbl_y1 = max(th + pad_y * 2, y1 - th - pad_y * 2 - 4)
                lbl_x2 = lbl_x1 + tw + pad_x * 2
                lbl_y2 = lbl_y1 + th + pad_y * 2

                draw_rounded_rectangle(
                    frame,
                    (lbl_x1, lbl_y1),
                    (lbl_x2, lbl_y2),
                    color,
                    thickness=-1,
                    radius=6,
                )
                text_draws.append(
                    {
                        "text": label,
                        "pos": (lbl_x1 + pad_x, lbl_y1 + pad_y - 2),
                        "size": 16,
                        "color": (255, 255, 255),
                        "stroke": False,
                    }
                )

            if button_clicked:
                button_clicked = False
                if last_recognized_name and checkin_tracker.is_checked_out_today(
                    last_recognized_name
                ):
                    toast_text = f"{last_recognized_name} 今日已签退，无需重复操作"
                    toast_until = time.time() + 2.5
                elif last_recognized_name and checkin_tracker.is_checked_in_today(
                    last_recognized_name
                ):
                    duration = attendance_db.check_out(last_recognized_name)
                    checkin_tracker.reset_checkin(last_recognized_name)
                    event_bus.checkout(last_recognized_name, 0, duration)
                    toast_text = (
                        f"【签退】{last_recognized_name} 成功，今日工作 {duration} 分钟"
                    )
                    toast_until = time.time() + 3.5
                elif last_recognized_name:
                    toast_text = f"提示: {last_recognized_name} 今日尚未打卡上班"
                    toast_until = time.time() + 2.5
                else:
                    toast_text = "识别对焦中...请正对摄像头后点击"
                    toast_until = time.time() + 2.5

            now = time.time()
            if now < toast_until and toast_text:
                _, _, tw, th = text_bbox(toast_text, 18)
                tx, ty = w // 2 - tw // 2, h - 110
                toast_overlay = frame.copy()
                draw_rounded_rectangle(
                    toast_overlay,
                    (tx - 20, ty - 12),
                    (tx + tw + 20, ty + th + 12),
                    (20, 20, 20),
                    -1,
                    radius=8,
                )
                cv2.addWeighted(toast_overlay, 0.8, frame, 0.2, 0, frame)
                draw_rounded_rectangle(
                    frame,
                    (tx - 20, ty - 12),
                    (tx + tw + 20, ty + th + 12),
                    (100, 240, 255),
                    1,
                    radius=8,
                )
                text_draws.append(
                    {
                        "text": toast_text,
                        "pos": (tx, ty),
                        "size": 18,
                        "color": (100, 240, 255),
                        "stroke": False,
                    }
                )

            if now < welcome_until:
                welcome_overlay = frame.copy()
                cv2.rectangle(welcome_overlay, (0, 56), (w, 110), (60, 140, 40), -1)
                cv2.addWeighted(welcome_overlay, 0.8, frame, 0.2, 0, frame)
                _, _, tw, th = text_bbox(welcome_text, 22)
                text_draws.append(
                    {
                        "text": welcome_text,
                        "pos": (w // 2 - tw // 2, 56 + (54 - th) // 2),
                        "size": 22,
                        "color": (255, 255, 255),
                        "stroke": False,
                    }
                )

            btn_text = "下班签退"
            _, _, btw, bth = text_bbox(btn_text, 18)
            b_pad_x, b_pad_y = 22, 12
            bx1, by1 = w - btw - b_pad_x * 2 - 20, h - bth - b_pad_y * 2 - 20
            bx2, by2 = w - 20, h - 20
            button_rect = [bx1, by1, bx2, by2]
            draw_rounded_rectangle(
                frame, (bx1, by1), (bx2, by2), COLOR_CYAN, -1, radius=20
            )
            text_draws.append(
                {
                    "text": btn_text,
                    "pos": (bx1 + b_pad_x, by1 + b_pad_y - 1),
                    "size": 18,
                    "color": (22, 22, 22),
                    "stroke": False,
                }
            )

            text_draws.append(
                {
                    "text": "SYSTEM DISPATCH",
                    "pos": (15, 8),
                    "size": 11,
                    "color": (160, 160, 160),
                }
            )
            text_draws.append(
                {
                    "text": f"底库: {len(db_embeddings)} 人  |  今日已签: {checkin_tracker.get_today_count()} 人",
                    "pos": (15, 24),
                    "size": 16,
                    "color": (245, 245, 245),
                }
            )

            fps_frames += 1
            if time.time() - fps_start >= 1.0:
                fps_display = f"FPS: {fps_frames}"
                fps_frames = 0
                fps_start = time.time()
            text_draws.append(
                {
                    "text": fps_display,
                    "pos": (w - 75, 20),
                    "size": 14,
                    "color": COLOR_CYAN,
                }
            )

            frame = draw_texts_on_frame(frame, text_draws)
            cv2.imshow(win_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == ord("Q"):
                break
            elif key == ord("r") or key == ord("R"):
                face_db.build(force=True)
                db_embeddings = face_db.get_all()

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    logger.info("=" * 50)
    logger.info("AI 智慧前台数字人系统 (MVP Optimized)")
    logger.info("=" * 50)

    face_db = FaceDatabase()
    face_db.build()
    db_embeddings = face_db.get_all()

    vector_db = None
    try:
        vector_db = VectorDB()
        if len(vector_db) > 0:
            pg_embeddings = vector_db.get_all_grouped()
            logger.info("pgvector 底库: %d 人", len(pg_embeddings))
            db_embeddings = pg_embeddings
        else:
            logger.info(
                "pgvector 为空, 使用 pickle 缓存底库: %d 人", len(db_embeddings)
            )
    except Exception as e:
        logger.warning("pgvector 不可用, 降级为 pickle 缓存: %s", e)

    recognizer = FaceRecognizer()
    recognizer.init_model()

    tracker = FaceTracker(detect_interval=DETECT_INTERVAL)

    attendance_db = AttendanceDB()
    checkin_tracker = CheckInTracker()
    checkin_tracker.cleanup()
    vote_buffer = VoteBuffer()
    rec_cache = RecognitionCache()
    event_bus = EventBus()

    redis_checkin = None
    try:
        redis_checkin = RedisCheckIn()
        checkin_tracker = redis_checkin
        logger.info("签到去重: Redis")
    except Exception as e:
        logger.warning("Redis 不可用, 降级为 JSON 文件去重: %s", e)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        logger.error("无法打开摄像头!")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if ENABLE_CAMERA:
        _run_gui_loop(
            cap,
            face_db,
            db_embeddings,
            recognizer,
            tracker,
            attendance_db,
            checkin_tracker,
            vote_buffer,
            rec_cache,
            event_bus,
        )
    else:
        _run_headless_loop(
            cap,
            face_db,
            db_embeddings,
            recognizer,
            tracker,
            attendance_db,
            checkin_tracker,
            vote_buffer,
            rec_cache,
            event_bus,
        )


if __name__ == "__main__":
    main()
