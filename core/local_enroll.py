"""Enroll an employee from local image files."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import warnings
from pathlib import Path

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CACHE_FILE,
    DETECTION_THRESHOLD,
    EMPLOYEES_DIR,
    INSIGHTFACE_MODEL,
    INSIGHTFACE_PROVIDERS,
)
from core.attendance_db import AttendanceDB
from core.vector_db import VectorDB

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
warnings.filterwarnings("ignore", category=FutureWarning)


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _safe_filename(value: str) -> str:
    return "".join("_" if ch in '<>:"/\\|?*\x00' else ch for ch in value)


def _collect_photos(payload: dict) -> list[Path]:
    paths: list[Path] = []
    for item in payload.get("photoPaths") or payload.get("photos") or []:
        paths.append(Path(item).expanduser().resolve())

    folder = payload.get("folder") or payload.get("photoDir")
    if folder:
        folder_path = Path(folder).expanduser().resolve()
        for path in sorted(folder_path.iterdir()):
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                paths.append(path)

    deduped = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def enroll_from_payload(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")

    photo_paths = _collect_photos(payload)
    if not photo_paths:
        raise ValueError("photoPaths or folder is required")

    missing = [str(path) for path in photo_paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing photos: " + ", ".join(missing[:5]))

    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=INSIGHTFACE_PROVIDERS)
    app.prepare(ctx_id=0, det_thresh=DETECTION_THRESHOLD)

    employee_dir = Path(EMPLOYEES_DIR) / name
    employee_dir.mkdir(parents=True, exist_ok=True)

    embeddings = []
    saved_paths = []
    skipped = []
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    for index, path in enumerate(photo_paths, start=1):
        img = cv2.imread(str(path))
        if img is None:
            skipped.append({"path": str(path), "reason": "cannot read image"})
            continue

        faces = app.get(img)
        if len(faces) == 0:
            skipped.append({"path": str(path), "reason": "no face detected"})
            continue

        face = max(faces, key=lambda item: float(item.det_score))
        suffix = path.suffix.lower() if path.suffix.lower() in IMAGE_EXTENSIONS else ".jpg"
        target = employee_dir / f"local_{index}_{timestamp}_{_safe_filename(path.stem)}{suffix}"
        shutil.copy2(path, target)
        saved_paths.append(str(target))
        embeddings.append((face.normed_embedding, "local", str(target)))

    if not embeddings:
        raise ValueError("no usable face embeddings extracted")

    vector_db = VectorDB()
    vector_db.upsert_employee(name, embeddings)

    attendance_db = AttendanceDB()
    inserted = attendance_db.register_employee(name)

    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

    return {
        "ok": True,
        "name": name,
        "inserted": inserted,
        "photos": len(photo_paths),
        "embeddings": len(embeddings),
        "savedPaths": saved_paths,
        "skipped": skipped,
    }


def main() -> int:
    if len(sys.argv) < 2:
        _print_json({"ok": False, "error": "payload json path is required"})
        return 2

    try:
        with open(sys.argv[1], "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
        _print_json(enroll_from_payload(payload))
        return 0
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
