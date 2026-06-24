"""UI 渲染: 科技感图形绘制工具"""

import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── 科技感高级配色 ──
COLOR_CYAN = (242, 194, 48)
COLOR_GREEN = (100, 215, 90)
COLOR_RED = (90, 90, 245)
COLOR_DARK_BAR = (30, 30, 30)

# ── 中文字体 ──
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


def draw_tech_bounding_box(
    img: np.ndarray,
    bbox: list[int],
    color: tuple[int, int, int],
    thickness: int = 2,
    length: int = 20,
) -> None:
    x1, y1, x2, y2 = bbox
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 1, lineType=cv2.LINE_AA)
    cv2.line(img, (x1, y1), (x1 + length, y1), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x1, y1), (x1, y1 + length), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2 - length, y1), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2, y1 + length), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1 + length, y2), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1, y2 - length), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2 - length, y2), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2, y2 - length), color, thickness, lineType=cv2.LINE_AA)


def draw_rounded_rectangle(
    img: np.ndarray,
    pt1: tuple[int, int],
    pt2: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int = -1,
    radius: int = 10,
) -> None:
    x1, y1 = pt1
    x2, y2 = pt2
    w, h = x2 - x1, y2 - y1
    radius = min(radius, abs(w) // 2, abs(h) // 2)
    if thickness < 0:
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
    else:
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
