"""Business services backing the FastAPI company integration layer."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import BinaryIO

import cv2

from config import (
    API_CAPTURE_CAMERA_INDEX,
    API_CAPTURE_WARMUP_FRAMES,
    API_UPLOAD_DIR,
    CACHE_FILE,
    EMPLOYEES_DIR,
)
from core.attendance_db import AttendanceDB
from core.events import EventBus
from core.local_enroll import IMAGE_EXTENSIONS, enroll_from_payload
from core.redis_checkin import RedisCheckIn
from core.vector_db import VectorDB


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def normalize_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        raise ApiError("name is required", 400)
    if any(ch in value for ch in '<>:"/\\|?*\x00'):
        raise ApiError("name contains invalid path characters", 400)
    return value


def _invalidate_face_cache() -> None:
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


class EmployeeService:
    def __init__(self):
        self.attendance_db = AttendanceDB()

    def list_employees(self) -> dict:
        mysql_names = set(self.attendance_db.list_employees())
        vector_names: set[str] = set()
        try:
            vector_names = set(VectorDB().list_employees())
        except Exception:
            vector_names = set()
        names = sorted(mysql_names | vector_names)
        return {"names": names, "count": len(names)}

    def create_employee(self, name: str) -> dict:
        name = normalize_name(name)
        inserted = self.attendance_db.register_employee(name)
        Path(EMPLOYEES_DIR, name).mkdir(parents=True, exist_ok=True)
        return {"name": name, "inserted": inserted}

    def enroll_employee(self, name: str, photo_paths: list[str], folder: str | None = None) -> dict:
        name = normalize_name(name)
        payload = {"name": name, "photoPaths": photo_paths, "folder": folder}
        result = enroll_from_payload(payload)
        return result

    def delete_employee(self, name: str) -> dict:
        name = normalize_name(name)
        deleted_from_mysql = self.attendance_db.delete_employee(name)
        deleted_from_vector = False
        try:
            vector_db = VectorDB()
            deleted_from_vector = name in set(vector_db.list_employees())
            vector_db.delete_employee(name)
        except Exception as exc:
            raise ApiError(f"delete face embeddings failed: {exc}", 500) from exc
        _invalidate_face_cache()
        return {
            "name": name,
            "deleted": deleted_from_mysql or deleted_from_vector,
            "deletedFromEmployeeTable": deleted_from_mysql,
            "deletedFromFaceDb": deleted_from_vector,
        }


class AttendanceService:
    def __init__(self):
        self.attendance_db = AttendanceDB()
        self.checkin_store = RedisCheckIn()
        self.event_bus = EventBus()

    def check_in(self, name: str, force: bool = False) -> dict:
        name = normalize_name(name)
        if not self.attendance_db.employee_exists(name):
            raise ApiError("employee not found", 404)
        if not force and self.checkin_store.is_checked_in_today(name):
            return {
                "name": name,
                "checkedIn": False,
                "reason": "already checked in today",
                "records": self.attendance_db.get_today_records(name),
            }
        row_id = self.attendance_db.check_in(name)
        self.checkin_store.mark_checked_in(name)
        self.event_bus.checkin(name, row_id, 1.0)
        return {"name": name, "checkedIn": True, "rowId": row_id}

    def check_out(self, name: str, force: bool = False) -> dict:
        name = normalize_name(name)
        if not self.attendance_db.employee_exists(name):
            raise ApiError("employee not found", 404)
        if not force and self.checkin_store.is_checked_out_today(name):
            return {
                "name": name,
                "checkedOut": False,
                "reason": "already checked out today",
                "records": self.attendance_db.get_today_records(name),
            }
        duration = self.attendance_db.check_out(name)
        if duration is None:
            raise ApiError("no open check-in record for today", 409)
        self.checkin_store.reset_checkin(name)
        self.event_bus.checkout(name, 0, duration)
        return {"name": name, "checkedOut": True, "durationMinutes": duration}

    def today_records(self, name: str) -> dict:
        name = normalize_name(name)
        return {"name": name, "records": self.attendance_db.get_today_records(name)}


class PhotoCaptureService:
    def __init__(self, employee_service: EmployeeService):
        self.employee_service = employee_service

    def save_upload(self, name: str, filename: str, file: BinaryIO) -> str:
        name = normalize_name(name)
        suffix = Path(filename or "").suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            raise ApiError("unsupported image type", 400)
        target_dir = Path(API_UPLOAD_DIR, "uploads", name, uuid.uuid4().hex)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"upload{suffix}"
        with open(target, "wb") as f:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        return str(target)

    def enroll_from_uploaded_files(self, name: str, files: list[tuple[str, BinaryIO]]) -> dict:
        paths = [self.save_upload(name, filename, file) for filename, file in files]
        return self.employee_service.enroll_employee(name, paths)

    def capture_and_enroll(
        self,
        name: str,
        camera_index: int | None = None,
        warmup_frames: int | None = None,
    ) -> dict:
        name = normalize_name(name)
        camera_index = API_CAPTURE_CAMERA_INDEX if camera_index is None else camera_index
        warmup_frames = (
            API_CAPTURE_WARMUP_FRAMES if warmup_frames is None else max(0, warmup_frames)
        )
        target_dir = Path(API_UPLOAD_DIR, "captures", name)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"capture_{time.strftime('%Y%m%d_%H%M%S')}.jpg"

        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            raise ApiError("camera open failed", 503)
        try:
            frame = None
            for _ in range(warmup_frames + 1):
                ok, current = cap.read()
                if ok:
                    frame = current
            if frame is None:
                raise ApiError("camera frame capture failed", 503)
            if not cv2.imwrite(str(target), frame):
                raise ApiError("capture image save failed", 500)
        finally:
            cap.release()

        result = self.employee_service.enroll_employee(name, [str(target)])
        result["capturePath"] = str(target)
        return result
