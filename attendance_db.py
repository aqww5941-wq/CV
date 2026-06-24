"""考勤数据库: SQLite 记录上下班打卡时间及工作时长"""

import os
import sqlite3
from datetime import date, datetime

from config import CACHE_DIR

DB_FILE = os.path.join(CACHE_DIR, "attendance.db")


class AttendanceDB:
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                check_in    TEXT    NOT NULL,
                check_out   TEXT,
                duration    INTEGER
            )
        """)
        self.conn.commit()

    def check_in(self, name: str) -> int:
        """上班打卡, 返回记录 ID"""
        today = date.today().isoformat()
        now = datetime.now().strftime("%H:%M:%S")
        cur = self.conn.execute(
            "INSERT INTO attendance (name, date, check_in) VALUES (?, ?, ?)",
            (name, today, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def check_out(self, name: str) -> int | None:
        """
        下班打卡: 找到此人今天最近一次未签退的记录, 写入签退时间和时长(分钟)。
        返回工作时长(分钟), 若无未签退记录返回 None。
        """
        today = date.today().isoformat()
        cur = self.conn.execute(
            "SELECT id, check_in FROM attendance "
            "WHERE name=? AND date=? AND check_out IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (name, today),
        )
        row = cur.fetchone()
        if row is None:
            return None

        row_id, check_in_str = row
        now = datetime.now().strftime("%H:%M:%S")
        t_in = datetime.strptime(check_in_str, "%H:%M:%S")
        t_out = datetime.strptime(now, "%H:%M:%S")
        duration = int((t_out - t_in).total_seconds() / 60)

        self.conn.execute(
            "UPDATE attendance SET check_out=?, duration=? WHERE id=?",
            (now, duration, row_id),
        )
        self.conn.commit()
        return duration

    def get_today_records(self, name: str) -> list[dict]:
        """查询某人今日所有打卡记录"""
        today = date.today().isoformat()
        cur = self.conn.execute(
            "SELECT id, check_in, check_out, duration "
            "FROM attendance WHERE name=? AND date=? ORDER BY id",
            (name, today),
        )
        return [
            {"id": r[0], "check_in": r[1], "check_out": r[2], "duration": r[3]}
            for r in cur.fetchall()
        ]
