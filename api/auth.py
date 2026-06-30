"""HMAC authentication helpers for protected integration APIs."""

from __future__ import annotations

import hashlib
import hmac
import time


def build_signature_payload(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
) -> bytes:
    prefix = f"{method.upper()}\n{path}\n{timestamp}\n".encode("utf-8")
    return prefix + body


def sign_request(
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
) -> str:
    payload = build_signature_payload(method, path, timestamp, body)
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def is_valid_timestamp(timestamp: str, tolerance_seconds: int) -> bool:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return False
    return abs(int(time.time()) - value) <= tolerance_seconds


def verify_request_signature(
    *,
    expected_key: str,
    secret: str,
    method: str,
    path: str,
    timestamp: str | None,
    body: bytes,
    api_key: str | None,
    signature: str | None,
    tolerance_seconds: int,
) -> bool:
    if not expected_key or not secret:
        return True
    if api_key != expected_key or not timestamp or not signature:
        return False
    if not is_valid_timestamp(timestamp, tolerance_seconds):
        return False
    expected_signature = sign_request(secret, method, path, timestamp, body)
    return hmac.compare_digest(signature, expected_signature)
