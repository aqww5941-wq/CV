"""人脸注册拍照工具: 正脸/左脸/右脸 各3张, 共9张, 录入 pgvector"""

from __future__ import annotations
from config import (
    AVATAR_SERVER_URL,
    EMPLOYEES_DIR,
    INSIGHTFACE_PROVIDERS,
    INSIGHTFACE_MODEL,
    DETECTION_THRESHOLD,
)
from core.vector_db import VectorDB

import logging
import os
import json
import shutil
import sys
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.env_loader import load_dotenv

load_dotenv()



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
ANGLE_READY_SECONDS = 2.0
AUTO_CAPTURE_INTERVAL_SECONDS = 0.8
EMPLOYEE_SYNC_TOKEN = os.environ.get("EMPLOYEE_SYNC_TOKEN", "")
ENABLE_TTS_PREWARM = os.environ.get("ENABLE_TTS_PREWARM") == "1"

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
    frame: np.ndarray,
    angle_name: str,
    hint: str,
    count: int,
    total: int,
    angle_count: int,
    next_capture_in: float,
) -> None:
    h, w = frame.shape[:2]
    bar_h = 70
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)
    cv2.line(frame, (0, bar_h), (w, bar_h), (48, 194, 242), 1, lineType=cv2.LINE_AA)
    _pil_text(frame, f"注册人脸 · {angle_name}", (15, 12), 20, (245, 245, 245))
    _pil_text(frame, f"进度: {count}/{total} 张", (15, 40), 18, (48, 194, 242))
    _pil_text(frame, hint, (w // 2 - 130, h // 2 + 10), 28, (48, 194, 242))
    if next_capture_in > 0:
        status = f"请保持姿势，{next_capture_in:.1f}s 后自动拍摄"
    else:
        status = f"自动拍摄中: {angle_count}/{PHOTOS_PER_ANGLE}"
    _pil_text(frame, status, (w // 2 - 180, h // 2 + 50), 22, (100, 215, 90))
    _pil_text(
        frame, "自动连拍，无需按空格 | Q 退出", (w // 2 - 160, h - 30), 18, (160, 160, 160)
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


def prewarm_employee_voice(name: str) -> dict:
    url = f"{AVATAR_SERVER_URL}/employees/sync"
    payload = json.dumps({"name": name}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if EMPLOYEE_SYNC_TOKEN:
        headers["x-api-key"] = EMPLOYEE_SYNC_TOKEN
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"语音生成接口失败 HTTP {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"无法连接数字人语音服务: {e}") from e

    if not data.get("ok"):
        raise RuntimeError(f"语音生成失败: {data}")
    return data


def delete_captured_photos(save_dir: str) -> None:
    if os.path.isdir(save_dir):
        shutil.rmtree(save_dir)


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
    angle_started_at = time.time()
    last_capture_at = 0.0
    frame_idx = 0
    cached_faces: list = []

    win_name = "人脸注册"
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
                cv2.waitKey(1200)
                break

            angle_key, hint = ANGLES[current_angle_idx]
            now = time.time()
            next_capture_in = max(0.0, ANGLE_READY_SECONDS - (now - angle_started_at))
            draw_guide(
                frame,
                angle_key,
                hint,
                len(photos),
                TOTAL_PHOTOS,
                angle_count,
                next_capture_in,
            )

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

            if (
                next_capture_in <= 0
                and cached_faces
                and now - last_capture_at >= AUTO_CAPTURE_INTERVAL_SECONDS
            ):
                face = max(cached_faces, key=lambda item: float(item.det_score))
                emb = face.normed_embedding
                ts = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{angle_key}_{angle_count + 1}_{ts}.jpg"
                filepath = os.path.join(save_dir, filename)
                cv2.imwrite(filepath, clean)
                photos.append((emb, angle_key, filepath))
                angle_count += 1
                last_capture_at = now
                logger.info("自动拍照: %s #%d -> %s", angle_key, angle_count, filename)

                h, w = frame.shape[:2]
                flash = frame.copy()
                cv2.rectangle(flash, (0, 0), (w, h), (255, 255, 255), -1)
                cv2.addWeighted(flash, 0.18, frame, 0.82, 0, frame)

                if angle_count >= PHOTOS_PER_ANGLE:
                    current_angle_idx += 1
                    angle_count = 0
                    angle_started_at = time.time()
                    last_capture_at = 0.0
                    cached_faces = []

            cv2.imshow(win_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == ord("Q"):
                break
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
        print(f"MySQL 同步失败: {e}")
        print(f"照片已保存到: {save_dir}")
        print("为保护流程完整性，照片未删除。请修复后重试。")
        sys.exit(1)

    if ENABLE_TTS_PREWARM:
        try:
            print("正在生成该员工姓名语音缓存...")
            result = prewarm_employee_voice(name)
            tts = result.get("results", [{}])[0].get("tts", {})
            print(
                "语音缓存生成完成: {generated}/{total} 新生成, {skipped} 已存在".format(
                    generated=tts.get("generated", 0),
                    total=tts.get("total", 0),
                    skipped=tts.get("skipped", 0),
                )
            )
        except Exception as e:
            print(f"语音缓存生成失败: {e}")
            print(f"照片已保存到: {save_dir}")
            print("为保护流程完整性，照片未删除。请修复后重试。")
            sys.exit(1)
    else:
        print("已跳过语音预生成，首次触发语音时会异步生成并缓存")

    try:
        delete_captured_photos(save_dir)
        print("已删除本次拍摄照片，仅保留向量和语音缓存")
    except Exception as e:
        print(f"照片删除失败，请手动删除 {save_dir}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
