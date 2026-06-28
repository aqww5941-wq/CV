"""OpenCV GUI loop for the local camera preview."""

from __future__ import annotations

import time

import cv2

from core.async_pipeline import AsyncPipelineWrapper
from ui.render import (
    COLOR_CYAN,
    COLOR_DARK_BAR,
    COLOR_GREEN,
    COLOR_RED,
    draw_rounded_rectangle,
    draw_tech_bounding_box,
    draw_texts_on_frame,
    text_bbox,
)


class OpenCVGuiLoop:
    """Owns the local preview window, drawing, and click interactions."""

    def __init__(
        self,
        cap,
        face_db,
        db_embeddings,
        pipeline,
        checkin_tracker,
    ):
        self.cap = cap
        self.face_db = face_db
        self.db_embeddings = db_embeddings
        self.pipeline = pipeline
        self.async_pipeline = AsyncPipelineWrapper(pipeline)
        self.checkin_tracker = checkin_tracker
        self.button_rect = [0, 0, 0, 0]
        self.button_clicked = False
        self.last_recognized_name = ""

    def run(self) -> None:
        win_name = "AI智慧前台数字人系统"
        cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(win_name, self._mouse_callback)

        welcome_text = ""
        welcome_until = 0.0
        toast_text = ""
        toast_until = 0.0

        fps_start = time.time()
        fps_frames = 0
        fps_display = ""

        self.async_pipeline.start()

        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    break

                frame = cv2.flip(frame, 1)
                self.async_pipeline.submit_frame(frame.copy())
                result = self.async_pipeline.get_result()
                h, w = frame.shape[:2]

                self.last_recognized_name = ""
                text_draws: list[dict] = []

                self._draw_top_bar(frame, w)
                if result is not None:
                    self._draw_faces(frame, result.faces, text_draws)

                    if result.checked_in_names:
                        welcome_text = (
                            f"欢迎回来, {result.checked_in_names[-1]}! 签到成功"
                        )
                        welcome_until = time.time() + 3.0

                if self.button_clicked:
                    self.button_clicked = False
                    toast_text, toast_until = self._handle_checkout_click()

                now = time.time()
                if now < toast_until and toast_text:
                    self._draw_toast(frame, text_draws, toast_text, w, h)

                if now < welcome_until:
                    self._draw_welcome(frame, text_draws, welcome_text, w)

                self._draw_checkout_button(frame, text_draws, w, h)
                self._draw_header_stats(text_draws, fps_display, w)

                fps_frames += 1
                if time.time() - fps_start >= 1.0:
                    fps_display = f"FPS: {fps_frames}"
                    fps_frames = 0
                    fps_start = time.time()

                frame = draw_texts_on_frame(frame, text_draws)
                cv2.imshow(win_name, frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q")):
                    break
                if key in (ord("r"), ord("R")):
                    self._rebuild_face_database()

        except KeyboardInterrupt:
            pass
        finally:
            self.async_pipeline.stop()
            self.cap.release()
            cv2.destroyAllWindows()

    def _mouse_callback(self, event, x, y, flags, param) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        bx1, by1, bx2, by2 = self.button_rect
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            self.button_clicked = True

    def _draw_top_bar(self, frame, width: int) -> None:
        overlay_bar = frame.copy()
        cv2.rectangle(overlay_bar, (0, 0), (width, 55), COLOR_DARK_BAR, -1)
        cv2.addWeighted(overlay_bar, 0.4, frame, 0.6, 0, frame)
        cv2.line(frame, (0, 55), (width, 55), COLOR_CYAN, 1, lineType=cv2.LINE_AA)

    def _draw_faces(self, frame, faces, text_draws: list[dict]) -> None:
        for face in faces:
            bbox = face.bbox
            color = COLOR_GREEN if face.recognized else COLOR_RED
            draw_tech_bounding_box(frame, bbox, color, thickness=3, length=18)

            if face.recognized:
                self.last_recognized_name = face.name or ""

            self._draw_face_label(frame, text_draws, face.label, bbox, color)

    def _draw_face_label(
        self,
        frame,
        text_draws: list[dict],
        label: str,
        bbox: list[int],
        color: tuple[int, int, int],
    ) -> None:
        x1, y1, _, _ = bbox
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

    def _handle_checkout_click(self) -> tuple[str, float]:
        name = self.last_recognized_name
        if name and self.checkin_tracker.is_checked_out_today(name):
            return f"{name} 今日已签退，无需重复操作", time.time() + 2.5
        if name and self.checkin_tracker.is_checked_in_today(name):
            duration = self.pipeline.checkout(name)
            return (
                f"【签退】{name} 成功，今日工作 {duration or 0} 分钟",
                time.time() + 3.5,
            )
        if name:
            return f"提示: {name} 今日尚未打卡上班", time.time() + 2.5
        return "识别对焦中...请正对摄像头后点击", time.time() + 2.5

    def _draw_toast(
        self,
        frame,
        text_draws: list[dict],
        toast_text: str,
        width: int,
        height: int,
    ) -> None:
        _, _, tw, th = text_bbox(toast_text, 18)
        tx, ty = width // 2 - tw // 2, height - 110
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

    def _draw_welcome(
        self,
        frame,
        text_draws: list[dict],
        welcome_text: str,
        width: int,
    ) -> None:
        welcome_overlay = frame.copy()
        cv2.rectangle(welcome_overlay, (0, 56), (width, 110), (60, 140, 40), -1)
        cv2.addWeighted(welcome_overlay, 0.8, frame, 0.2, 0, frame)
        _, _, tw, th = text_bbox(welcome_text, 22)
        text_draws.append(
            {
                "text": welcome_text,
                "pos": (width // 2 - tw // 2, 56 + (54 - th) // 2),
                "size": 22,
                "color": (255, 255, 255),
                "stroke": False,
            }
        )

    def _draw_checkout_button(
        self,
        frame,
        text_draws: list[dict],
        width: int,
        height: int,
    ) -> None:
        btn_text = "下班签退"
        _, _, btw, bth = text_bbox(btn_text, 18)
        b_pad_x, b_pad_y = 22, 12
        bx1 = width - btw - b_pad_x * 2 - 20
        by1 = height - bth - b_pad_y * 2 - 20
        bx2, by2 = width - 20, height - 20
        self.button_rect = [bx1, by1, bx2, by2]

        draw_rounded_rectangle(frame, (bx1, by1), (bx2, by2), COLOR_CYAN, -1, radius=20)
        text_draws.append(
            {
                "text": btn_text,
                "pos": (bx1 + b_pad_x, by1 + b_pad_y - 1),
                "size": 18,
                "color": (22, 22, 22),
                "stroke": False,
            }
        )

    def _draw_header_stats(
        self,
        text_draws: list[dict],
        fps_display: str,
        width: int,
    ) -> None:
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
                "text": (
                    f"底库: {len(self.db_embeddings)} 人  |  "
                    f"今日已签: {self.checkin_tracker.get_today_count()} 人"
                ),
                "pos": (15, 24),
                "size": 16,
                "color": (245, 245, 245),
            }
        )
        text_draws.append(
            {
                "text": fps_display,
                "pos": (width - 75, 20),
                "size": 14,
                "color": COLOR_CYAN,
            }
        )

    def _rebuild_face_database(self) -> None:
        self.face_db.build(force=True)
        self.db_embeddings = self.face_db.get_all()
        self.pipeline.update_embeddings(self.db_embeddings)
