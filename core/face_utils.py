"""Small helpers shared by face recognition loops."""

from config import STRANGER_EDGE_MARGIN, STRANGER_MIN_FACE_SIZE


def is_complete_face_for_stranger(bbox: list[int], frame_shape) -> bool:
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = bbox
    face_w = max(0, x2 - x1)
    face_h = max(0, y2 - y1)

    if min(face_w, face_h) < STRANGER_MIN_FACE_SIZE:
        return False
    return (
        x1 >= STRANGER_EDGE_MARGIN
        and y1 >= STRANGER_EDGE_MARGIN
        and x2 <= w - STRANGER_EDGE_MARGIN
        and y2 <= h - STRANGER_EDGE_MARGIN
    )

