"""Employee sync CLI for the avatar service."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.attendance_db import AttendanceDB


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def register_employee(name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("name is required")

    db = AttendanceDB()
    inserted = db.register_employee(name)
    _print_json({"ok": True, "name": name, "inserted": inserted})


def list_employees() -> None:
    db = AttendanceDB()
    names = db.list_employees()
    _print_json({"ok": True, "names": names})


def main() -> int:
    if len(sys.argv) < 2:
        _print_json({"ok": False, "error": "missing command"})
        return 2

    command = sys.argv[1]
    try:
        if command == "--register":
            if len(sys.argv) < 3:
                raise ValueError("name is required")
            register_employee(sys.argv[2])
            return 0
        if command == "--list":
            list_employees()
            return 0
        raise ValueError(f"unknown command: {command}")
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
