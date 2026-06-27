"""Small helpers shared by face recognition loops."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import (
    FACE_EDGE_MARGIN,
    FACE_MAX_POSE_IMBALANCE,
    FACE_MIN_DET_SCORE,
    FACE_MIN_EYE_DISTANCE,
    FACE_MIN_MATCH_SIZE,
    STRANGER_EDGE_MARGIN,
    STRANGER_MIN_FACE_SIZE,
)


@dataclass(frozen=True)
class FaceQuality:
    passed: bool
    label: str


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


def check_face_quality(face: dict, frame_shape) -> FaceQuality:
    bbox = face["bbox"]
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = bbox
    face_w = max(0, x2 - x1)
    face_h = max(0, y2 - y1)

    if min(face_w, face_h) < FACE_MIN_MATCH_SIZE:
        return FaceQuality(False, "请靠近摄像头")

    if (
        x1 < FACE_EDGE_MARGIN
        or y1 < FACE_EDGE_MARGIN
        or x2 > w - FACE_EDGE_MARGIN
        or y2 > h - FACE_EDGE_MARGIN
    ):
        return FaceQuality(False, "请站到画面中央")

    if float(face.get("det_score") or 0.0) < FACE_MIN_DET_SCORE:
        return FaceQuality(False, "请正对摄像头")

    kps = face.get("kps")
    if kps is not None and not _is_frontal_landmark_layout(kps):
        return FaceQuality(False, "请正对摄像头")

    return FaceQuality(True, "")


def _is_frontal_landmark_layout(kps) -> bool:
    points = np.asarray(kps, dtype=np.float32)
    if points.shape[0] < 3:
        return True

    left_eye = points[0]
    right_eye = points[1]
    nose = points[2]
    eye_distance = float(np.linalg.norm(left_eye - right_eye))
    if eye_distance < FACE_MIN_EYE_DISTANCE:
        return False

    eye_mid_x = float((left_eye[0] + right_eye[0]) / 2.0)
    pose_imbalance = abs(float(nose[0]) - eye_mid_x) / eye_distance
    return pose_imbalance <= FACE_MAX_POSE_IMBALANCE
