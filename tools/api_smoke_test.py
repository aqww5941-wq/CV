"""Smoke-test the FastAPI company integration endpoints with HMAC signing."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import API_KEY, API_SECRET


@dataclass
class TestResult:
    name: str
    ok: bool
    status: int | None
    detail: str


class SignedApiClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        signed: bool = True,
    ) -> tuple[int, dict | str]:
        body = b""
        headers: dict[str, str] = {}
        if json_body is not None:
            body = json.dumps(
                json_body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            body = raw_body
            if content_type:
                headers["Content-Type"] = content_type

        if signed:
            headers.update(self._signed_headers(method, path, body))

        req = Request(
            f"{self.base_url}{path}",
            data=body if method.upper() not in {"GET", "DELETE"} or body else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return resp.status, self._decode_response(resp.read())
        except HTTPError as exc:
            return exc.code, self._decode_response(exc.read())
        except URLError as exc:
            raise RuntimeError(f"request failed: {exc}") from exc

    def _signed_headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        payload = f"{method.upper()}\n{path}\n{timestamp}\n".encode("utf-8") + body
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return {
            "x-api-key": self.api_key,
            "x-timestamp": timestamp,
            "x-signature": signature,
        }

    @staticmethod
    def _decode_response(raw: bytes) -> dict | str:
        text = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


def multipart_body(fields: dict[str, str], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----cv-api-smoke-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for field_name, path in files:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def record(
    results: list[TestResult],
    name: str,
    status: int | None,
    payload: dict | str,
    expected: set[int],
) -> None:
    ok = status in expected
    detail = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    results.append(TestResult(name=name, ok=ok, status=status, detail=detail[:500]))


def run(args: argparse.Namespace) -> int:
    api_key = args.api_key or API_KEY
    api_secret = args.api_secret or API_SECRET
    if not api_key or not api_secret:
        print("API_KEY/API_SECRET is required. Set .env or pass --api-key/--api-secret.")
        return 2

    client = SignedApiClient(args.base_url, api_key, api_secret, args.timeout)
    results: list[TestResult] = []
    employee_name = args.name
    encoded_name = quote(employee_name, safe="")

    status, payload = client.request("GET", "/health", signed=False)
    record(results, "GET /health", status, payload, {200})

    status, payload = client.request("GET", "/api/v1/employees", signed=False)
    record(results, "GET /api/v1/employees unsigned should reject", status, payload, {401})

    status, payload = client.request("GET", "/api/v1/employees")
    record(results, "GET /api/v1/employees", status, payload, {200})

    status, payload = client.request(
        "POST",
        "/api/v1/employees",
        json_body={"name": employee_name},
    )
    record(results, "POST /api/v1/employees", status, payload, {200})

    status, payload = client.request("GET", f"/api/v1/attendance/today/{encoded_name}")
    record(results, "GET /api/v1/attendance/today/{name}", status, payload, {200})

    status, payload = client.request(
        "POST",
        "/api/v1/attendance/check-in",
        json_body={"name": employee_name, "force": True},
    )
    record(results, "POST /api/v1/attendance/check-in", status, payload, {200})

    status, payload = client.request("GET", f"/api/v1/attendance/today/{encoded_name}")
    record(results, "GET /api/v1/attendance/today/{name} after check-in", status, payload, {200})

    status, payload = client.request(
        "POST",
        "/api/v1/attendance/check-out",
        json_body={"name": employee_name, "force": True},
    )
    record(results, "POST /api/v1/attendance/check-out", status, payload, {200})

    if args.photo:
        photo = Path(args.photo).expanduser().resolve()
        if not photo.exists():
            results.append(TestResult("photo-dependent tests", False, None, f"photo not found: {photo}"))
        else:
            status, payload = client.request(
                "POST",
                "/api/v1/employees/enroll-local",
                json_body={"name": employee_name, "photo_paths": [str(photo)]},
            )
            record(results, "POST /api/v1/employees/enroll-local", status, payload, {200})

            body, content_type = multipart_body({"name": employee_name}, [("files", photo)])
            status, payload = client.request(
                "POST",
                "/api/v1/employees/enroll-upload",
                raw_body=body,
                content_type=content_type,
            )
            record(results, "POST /api/v1/employees/enroll-upload", status, payload, {200})
    else:
        results.append(
            TestResult(
                "POST /api/v1/employees/enroll-local",
                True,
                None,
                "skipped: pass --photo to test face enrollment",
            )
        )
        results.append(
            TestResult(
                "POST /api/v1/employees/enroll-upload",
                True,
                None,
                "skipped: pass --photo to test upload enrollment",
            )
        )

    if args.include_camera:
        status, payload = client.request(
            "POST",
            "/api/v1/employees/capture-enroll",
            json_body={
                "name": employee_name,
                "camera_index": args.camera_index,
                "warmup_frames": args.warmup_frames,
            },
        )
        record(results, "POST /api/v1/employees/capture-enroll", status, payload, {200})
    else:
        results.append(
            TestResult(
                "POST /api/v1/employees/capture-enroll",
                True,
                None,
                "skipped: pass --include-camera to test camera capture",
            )
        )

    if args.delete:
        status, payload = client.request("DELETE", f"/api/v1/employees/{encoded_name}")
        record(results, "DELETE /api/v1/employees/{name}", status, payload, {200})
    else:
        results.append(
            TestResult(
                "DELETE /api/v1/employees/{name}",
                True,
                None,
                "skipped: pass --delete to remove the test employee",
            )
        )

    failures = [item for item in results if not item.ok]
    for item in results:
        mark = "PASS" if item.ok else "FAIL"
        status_text = "-" if item.status is None else str(item.status)
        print(f"[{mark}] {item.name} status={status_text} {item.detail}")

    print(f"\nsummary: {len(results) - len(failures)}/{len(results)} passed")
    return 1 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--api-secret", default="")
    parser.add_argument("--name", default=f"api_smoke_{int(time.time())}")
    parser.add_argument("--photo", default="", help="Face photo path for enroll-local/enroll-upload")
    parser.add_argument("--include-camera", action="store_true")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--warmup-frames", type=int, default=8)
    parser.add_argument("--delete", action="store_true", help="Delete the smoke-test employee at the end")
    parser.add_argument("--timeout", type=int, default=180)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
