"""人脸注册拍照工具: 正脸/左脸/右脸 各3张, 共9张, 录入 pgvector"""

from __future__ import annotations

import logging
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    EMPLOYEES_DIR,
    INSIGHTFACE_PROVIDERS,
    INSIGHTFACE_MODEL,
    DETECTION_THRESHOLD,
)
from core.vector_db import VectorDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("capture")

ANGLES = [
    ("zheng", "请正对摄像头"),
    ("zuo", "请缓慢转向左侧"),
    ("you", "请缓慢转向右侧"),
]
PHOTOS_PER_ANGLE = 3
TOTAL_PHOTOS = len(ANGLES) * PHOTOS_PER_ANGLE
DETECT_EVERY_N = 5

_FONT_PATH = None
for _fp in [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]:
    if os.path.exists(_fp):
        _FONT_PATH = _fp
        break


def _pil_text(img: np.ndarray, text: str, pos: tuple, size: int, color: tuple) -> None:
    if _FONT_PATH is None:
        cv2.putText(
            img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, size / 20, color, 1, cv2.LINE_AA
        )
        return
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = ImageFont.truetype(_FONT_PATH, size)
    draw.text(pos, text, font=font, fill=color)
    rgb = np.array(pil_img)
    img[:] = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def draw_guide(
    frame: np.ndarray, angle_name: str, hint: str, count: int, total: int
) -> None:
    h, w = frame.shape[:2]
    bar_h = 70
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)
    cv2.line(frame, (0, bar_h), (w, bar_h), (48, 194, 242), 1, lineType=cv2.LINE_AA)
    _pil_text(frame, f"注册人脸 · {angle_name}", (15, 12), 20, (245, 245, 245))
    _pil_text(frame, f"进度: {count}/{total} 张", (15, 40), 18, (48, 194, 242))
    _pil_text(frame, hint, (w // 2 - 120, h // 2 + 30), 28, (48, 194, 242))
    _pil_text(
        frame, "按 SPACE 拍照 | Q 退出", (w // 2 - 130, h - 30), 18, (160, 160, 160)
    )


def draw_done(frame: np.ndarray) -> None:
    h, w = frame.shape[:2]
    _pil_text(
        frame,
        "全部拍摄完成! 按任意键退出",
        (w // 2 - 180, h // 2 - 20),
        28,
        (100, 215, 90),
    )


def main():
    name = input("请输入员工姓名: ").strip()
    if not name:
        print("姓名不能为空")
        sys.exit(1)

    save_dir = os.path.join(EMPLOYEES_DIR, name)
    os.makedirs(save_dir, exist_ok=True)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("无法打开摄像头!")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=INSIGHTFACE_PROVIDERS)
    app.prepare(ctx_id=0, det_thresh=DETECTION_THRESHOLD)
    logger.info("模型就绪")

    photos: list[tuple[np.ndarray, str, str]] = []
    current_angle_idx = 0
    angle_count = 0
    frame_idx = 0
    cached_faces: list = []

    win_name = f"人脸注册"
    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            clean = frame.copy()
            frame_idx += 1

            if current_angle_idx >= len(ANGLES):
                draw_done(frame)
                cv2.imshow(win_name, frame)
                cv2.waitKey(0)
                break

            angle_key, hint = ANGLES[current_angle_idx]
            draw_guide(frame, angle_key, hint, len(photos), TOTAL_PHOTOS)

            if frame_idx % DETECT_EVERY_N == 0:
                cached_faces = app.get(frame)
            for face in cached_faces:
                bbox = face.bbox.astype(int)
                cv2.rectangle(
                    frame,
                    (bbox[0], bbox[1]),
                    (bbox[2], bbox[3]),
                    (100, 215, 90),
                    2,
                    lineType=cv2.LINE_AA,
                )

            cv2.imshow(win_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == ord("Q"):
                break
            elif key == ord(" "):
                faces = app.get(frame)
                if len(faces) > 0:
                    emb = faces[0].normed_embedding
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"{angle_key}_{angle_count + 1}_{ts}.jpg"
                    filepath = os.path.join(save_dir, filename)
                    cv2.imwrite(filepath, clean)
                    photos.append((emb, angle_key, filepath))
                    angle_count += 1
                    logger.info("拍照: %s #%d -> %s", angle_key, angle_count, filename)
                    if angle_count >= PHOTOS_PER_ANGLE:
                        current_angle_idx += 1
                        angle_count = 0
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if len(photos) == 0:
        print("未拍摄任何照片, 退出")
        sys.exit(0)

    print(f"\n共拍摄 {len(photos)} 张照片, 正在写入 pgvector...")
    try:
        db = VectorDB()
        db.upsert_employee(name, photos)
        print(f"注册成功! {name} 已录入 pgvector ({len(photos)} 条向量)")
    except Exception as e:
        print(f"pgvector 写入失败: {e}")
        print(f"照片已保存到: {save_dir}")
        print("可以稍后手动运行注册")
        sys.exit(1)

    try:
        from core.attendance_db import AttendanceDB

        att_db = AttendanceDB()
        registered = att_db.register_employee(name)
        if registered:
            print(f"MySQL 同步成功: {name} 已录入 employees 表")
        else:
            print(f"MySQL: {name} 已存在, 跳过")
    except Exception as e:
        print(f"MySQL 同步失败 (不影响识别): {e}")


if __name__ == "__main__":
    main()
