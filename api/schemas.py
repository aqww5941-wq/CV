"""Request and response schemas for the company integration API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmployeeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="员工姓名")


class EmployeeEnrollRequest(BaseModel):
    name: str = Field(..., min_length=1, description="员工姓名")
    photo_paths: list[str] = Field(default_factory=list, description="服务端本地照片路径")
    folder: str | None = Field(default=None, description="服务端本地照片目录")


class CaptureEnrollRequest(BaseModel):
    name: str = Field(..., min_length=1, description="员工姓名")
    camera_index: int | None = Field(default=None, description="摄像头索引")
    warmup_frames: int | None = Field(default=None, ge=0, le=60, description="拍照前预热帧数")


class AttendanceRequest(BaseModel):
    name: str = Field(..., min_length=1, description="员工姓名")
    force: bool = Field(default=False, description="忽略当天签到/签退去重")


class ApiResponse(BaseModel):
    ok: bool
    message: str | None = None
    data: dict | list | None = None
