"""FastAPI app for employee enrollment and attendance integration."""

from __future__ import annotations

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from api.auth import verify_request_signature
from api.schemas import (
    AttendanceRequest,
    CaptureEnrollRequest,
    EmployeeCreateRequest,
    EmployeeEnrollRequest,
)
from api.services import (
    ApiError,
    AttendanceService,
    EmployeeService,
    PhotoCaptureService,
)
from config import API_CORS_ORIGINS, API_KEY, API_SECRET, API_SIGNATURE_TOLERANCE_SECONDS

app = FastAPI(
    title="CV Company Integration API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_api_signature(
    request: Request,
    x_api_key: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
) -> None:
    if not API_KEY or not API_SECRET:
        return
    body = await request.body()
    if verify_request_signature(
        expected_key=API_KEY,
        secret=API_SECRET,
        method=request.method,
        path=request.url.path,
        timestamp=x_timestamp,
        body=body,
        api_key=x_api_key,
        signature=x_signature,
        tolerance_seconds=API_SIGNATURE_TOLERANCE_SECONDS,
    ):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


def handle_api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ApiError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "company-integration-api"}


@app.get("/api/v1/employees", dependencies=[Depends(require_api_signature)])
async def list_employees() -> dict:
    try:
        data = await run_in_threadpool(lambda: EmployeeService().list_employees())
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.post("/api/v1/employees", dependencies=[Depends(require_api_signature)])
async def create_employee(payload: EmployeeCreateRequest) -> dict:
    try:
        data = await run_in_threadpool(lambda: EmployeeService().create_employee(payload.name))
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.post("/api/v1/employees/enroll-local", dependencies=[Depends(require_api_signature)])
async def enroll_employee(payload: EmployeeEnrollRequest) -> dict:
    try:
        data = await run_in_threadpool(
            lambda: EmployeeService().enroll_employee(
                payload.name,
                payload.photo_paths,
                payload.folder,
            )
        )
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.post("/api/v1/employees/enroll-upload", dependencies=[Depends(require_api_signature)])
async def enroll_employee_from_upload(
    name: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict:
    try:
        upload_files = [(item.filename or "", item.file) for item in files]
        data = await run_in_threadpool(
            lambda: PhotoCaptureService(EmployeeService()).enroll_from_uploaded_files(
                name,
                upload_files,
            )
        )
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.post("/api/v1/employees/capture-enroll", dependencies=[Depends(require_api_signature)])
async def capture_and_enroll(payload: CaptureEnrollRequest) -> dict:
    try:
        data = await run_in_threadpool(
            lambda: PhotoCaptureService(EmployeeService()).capture_and_enroll(
                payload.name,
                payload.camera_index,
                payload.warmup_frames,
            )
        )
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.delete("/api/v1/employees/{name}", dependencies=[Depends(require_api_signature)])
async def delete_employee(name: str) -> dict:
    try:
        data = await run_in_threadpool(lambda: EmployeeService().delete_employee(name))
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.post("/api/v1/attendance/check-in", dependencies=[Depends(require_api_signature)])
async def check_in(payload: AttendanceRequest) -> dict:
    try:
        data = await run_in_threadpool(
            lambda: AttendanceService().check_in(
                payload.name,
                payload.force,
            )
        )
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.post("/api/v1/attendance/check-out", dependencies=[Depends(require_api_signature)])
async def check_out(payload: AttendanceRequest) -> dict:
    try:
        data = await run_in_threadpool(
            lambda: AttendanceService().check_out(
                payload.name,
                payload.force,
            )
        )
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc


@app.get("/api/v1/attendance/today/{name}", dependencies=[Depends(require_api_signature)])
async def today_records(name: str) -> dict:
    try:
        data = await run_in_threadpool(lambda: AttendanceService().today_records(name))
        return {"ok": True, "data": data}
    except Exception as exc:
        raise handle_api_error(exc) from exc
