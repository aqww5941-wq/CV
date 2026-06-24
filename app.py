"""AI 智慧前台数字人系统 - 科技感 UI 优化版"""

import logging
import os
import sys
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import (
    CAMERA_INDEX,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    MATCH_THRESHOLD,
    COLOR_RECOGNIZED,
    COLOR_STRANGER,
    COLOR_WELCOME,
    ENABLE_CAMERA,
    ALLOW_REPEAT_CHECKIN,
    DETECT_INTERVAL,
    VOTE_WINDOW,
)
from attendance_db import AttendanceDB
from face_db import FaceDatabase
from face_recognition import CheckInTracker, FaceRecognizer, FaceTracker, VoteBuffer
from sound import play_welcome

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

# ──────────────────── 科技感高级配色 ────────────────────
# 告别高饱和度纯色，改用现代扁平化 UI 常用色
COLOR_CYAN = (242, 194, 48)  # BGR 科技青 (RGB: 48, 194, 242)
COLOR_GREEN = (100, 215, 90)  # BGR 柔和绿 (RGB: 90, 215, 100)
COLOR_RED = (90, 90, 245)  # BGR 柔和红 (RGB: 245, 90, 90)
COLOR_DARK_BAR = (30, 30, 30)  # 状态栏暗色底

# ──────────────────── 中文字体 ────────────────────
_FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONT_CACHE:
        for fp in _FONT_PATHS:
            if os.path.exists(fp):
                _FONT_CACHE[size] = ImageFont.truetype(fp, size)
                break
        else:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def text_bbox(text: str, font_size: int) -> tuple[int, int, int, int]:
    font = _get_font(font_size)
    img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(img)
    return draw.textbbox((0, 0), text, font=font)


def pil_draw_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    font_size: int,
    color: tuple[int, int, int],
    stroke: bool = False,
) -> tuple[int, int]:
    font = _get_font(font_size)
    bbox = draw.textbbox(pos, text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if stroke:
        draw.text(
            pos, text, font=font, fill=color, stroke_width=1, stroke_fill=(15, 15, 15)
        )
    else:
        draw.text(pos, text, font=font, fill=color)
    return tw, th


# ──────────────────── 科技感图形绘制工具 ────────────────────


def draw_tech_bounding_box(img, bbox, color, thickness=2, length=20):
    """绘制高科技感的四角包边人脸框，而非死板的矩形板"""
    x1, y1, x2, y2 = bbox
    # 浅色背景骨架（可选，这里用半透明弱化）
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 1, lineType=cv2.LINE_AA)

    # 左上角
    cv2.line(img, (x1, y1), (x1 + length, y1), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x1, y1), (x1, y1 + length), color, thickness, lineType=cv2.LINE_AA)
    # 右上角
    cv2.line(img, (x2, y1), (x2 - length, y1), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2, y1 + length), color, thickness, lineType=cv2.LINE_AA)
    # 左下角
    cv2.line(img, (x1, y2), (x1 + length, y2), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1, y2 - length), color, thickness, lineType=cv2.LINE_AA)
    # 右下角
    cv2.line(img, (x2, y2), (x2 - length, y2), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2, y2 - length), color, thickness, lineType=cv2.LINE_AA)


def draw_rounded_rectangle(img, pt1, pt2, color, thickness=-1, radius=10):
    """使用 OpenCV 原生函数绘制现代圆角矩形（支持实心和空心）"""
    x1, y1 = pt1
    x2, y2 = pt2

    # 限制半径不超出范围
    w, h = x2 - x1, y2 - y1
    radius = min(radius, abs(w) // 2, abs(h) // 2)

    if thickness < 0:  # 实心
        cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
        cv2.circle(
            img, (x1 + radius, y1 + radius), radius, color, -1, lineType=cv2.LINE_AA
        )
        cv2.circle(
            img, (x2 - radius, y1 + radius), radius, color, -1, lineType=cv2.LINE_AA
        )
        cv2.circle(
            img, (x1 + radius, y2 - radius), radius, color, -1, lineType=cv2.LINE_AA
        )
        cv2.circle(
            img, (x2 - radius, y2 - radius), radius, color, -1, lineType=cv2.LINE_AA
        )
    else:  # 空心
        cv2.circle(
            img,
            (x1 + radius, y1 + radius),
            radius,
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.circle(
            img,
            (x2 - radius, y1 + radius),
            radius,
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.circle(
            img,
            (x1 + radius, y2 - radius),
            radius,
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.circle(
            img,
            (x2 - radius, y2 - radius),
            radius,
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            img,
            (x1 + radius, y1),
            (x2 - radius, y1),
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            img,
            (x1 + radius, y2),
            (x2 - radius, y2),
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            img,
            (x1, y1 + radius),
            (x1, y2 - radius),
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            img,
            (x2, y1 + radius),
            (x2, y2 - radius),
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )


# ──────────────────── 按钮状态与回调 ────────────────────
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


def draw_texts_on_frame(frame: np.ndarray, draw_calls: list[dict]) -> np.ndarray:
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    for dc in draw_calls:
        pil_draw_text(
            draw,
            dc["pos"],
            dc["text"],
            dc["size"],
            dc["color"],
            dc.get("stroke", False),
        )
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


# ──────────────────── 主流程 ────────────────────


def _run_headless_loop(
    cap,
    face_db,
    db_embeddings,
    recognizer,
    tracker,
    attendance_db,
    checkin_tracker,
    vote_buffer,
):
    """无 GUI 模式：摄像头静默运行，控制台输出打卡事件，Ctrl+C 退出"""
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

            for face in faces:
                embedding = face["embedding"]
                track_id = face["track_id"]
                name, similarity = recognizer.match(embedding, db_embeddings)

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

                if ALLOW_REPEAT_CHECKIN or recognizer.should_welcome(voted_name):
                    row_id = attendance_db.check_in(voted_name)
                    checkin_tracker.mark_checked_in(voted_name)
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
                    sum(1 for v in checkin_tracker._records.values() for _ in v),
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
):
    """GUI 模式：摄像头实时画面 + 科技感 UI 叠加层"""
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

            # ── 1. 顶部半透明磨砂质感状态栏 ──
            overlay_bar = frame.copy()
            cv2.rectangle(overlay_bar, (0, 0), (w, 55), COLOR_DARK_BAR, -1)
            cv2.addWeighted(overlay_bar, 0.4, frame, 0.6, 0, frame)
            cv2.line(frame, (0, 55), (w, 55), COLOR_CYAN, 1, lineType=cv2.LINE_AA)

            # ── 2. 人脸检测与高科技框 ──
            active_ids = {face["track_id"] for face in faces}
            vote_buffer.cleanup_inactive(active_ids)

            for face in faces:
                bbox = face["bbox"]
                embedding = face["embedding"]
                track_id = face["track_id"]
                name, similarity = recognizer.match(embedding, db_embeddings)
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
                        if voted_name is not None and (
                            ALLOW_REPEAT_CHECKIN
                            or recognizer.should_welcome(voted_name)
                        ):
                            row_id = attendance_db.check_in(voted_name)
                            checkin_tracker.mark_checked_in(voted_name)
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

            # ── 3. 逻辑处理: 下班打卡按钮事件 ──
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

            # ── 4. 浮动 Toast 提示渲染 ──
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

            # ── 5. 全屏欢迎横幅 ──
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

            # ── 6. 底部【下班签退】按钮 ──
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

            # ── 7. 顶部状态栏文字 ──
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
                    "text": f"底库: {len(db_embeddings)} 人  |  今日已签: {sum(1 for v in checkin_tracker._records.values() for _ in v)} 人",
                    "pos": (15, 24),
                    "size": 16,
                    "color": (245, 245, 245),
                }
            )

            # ── 8. FPS ──
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

    recognizer = FaceRecognizer()
    recognizer.init_model()

    tracker = FaceTracker(detect_interval=DETECT_INTERVAL)

    attendance_db = AttendanceDB()
    checkin_tracker = CheckInTracker()
    checkin_tracker.cleanup()
    vote_buffer = VoteBuffer()

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
        )


if __name__ == "__main__":
    main()
