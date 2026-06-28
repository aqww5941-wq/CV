"""考勤数据库: MySQL 记录上下班打卡时间及工作时长"""

from __future__ import annotations

import logging
import queue
import threading
from contextlib import contextmanager
from datetime import date, datetime

import pymysql

from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
    MYSQL_CHARSET,
    MYSQL_POOL_SIZE,
)

logger = logging.getLogger(__name__)


class MySQLConnectionPool:
    """Small lazy PyMySQL pool for shared app workers."""

    def __init__(self, database: str, max_size: int):
        self.database = database
        self.max_size = max(1, max_size)
        self._idle: queue.Queue[pymysql.connections.Connection] = queue.Queue(
            maxsize=self.max_size
        )
        self._created = 0
        self._lock = threading.Lock()

    def get(self) -> pymysql.connections.Connection:
        try:
            conn = self._idle.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self.max_size:
                    self._created += 1
                    try:
                        return AttendanceDB._create_conn(database=self.database)
                    except Exception:
                        self._created -= 1
                        raise
            conn = self._idle.get()

        conn.ping(reconnect=True)
        return conn

    def put(self, conn: pymysql.connections.Connection) -> None:
        if getattr(conn, "open", False):
            self._idle.put(conn)
            return
        with self._lock:
            self._created = max(0, self._created - 1)


class AttendanceDB:
    """MySQL 考勤数据库"""

    def __init__(self):
        conn = self._create_conn()
        try:
            self._ensure_database(conn)
        finally:
            conn.close()
        self._pool = MySQLConnectionPool(MYSQL_DATABASE, MYSQL_POOL_SIZE)
        self._init_table()
        logger.info("MySQL 连接成功: %s:%s/%s", MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE)

    @staticmethod
    def _create_conn(database: str | None = None) -> pymysql.connections.Connection:
        kwargs = dict(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset=MYSQL_CHARSET,
            autocommit=True,
            cursorclass=pymysql.cursors.Cursor,
        )
        if database:
            kwargs["database"] = database
        return pymysql.connect(**kwargs)

    @contextmanager
    def _connection(self):
        conn = self._pool.get()
        try:
            yield conn
        finally:
            self._pool.put(conn)

    def _ensure_database(self, conn):
        cur = conn.cursor()
        cur.execute(
            "CREATE DATABASE IF NOT EXISTS `%s`"
            " DEFAULT CHARACTER SET utf8mb4"
            " DEFAULT COLLATE utf8mb4_unicode_ci" % MYSQL_DATABASE
        )
        cur.close()

    def _init_table(self):
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    name        VARCHAR(255) NOT NULL,
                    date        VARCHAR(10)  NOT NULL,
                    check_in    VARCHAR(8)   NOT NULL,
                    check_out   VARCHAR(8),
                    duration    INT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            self._ensure_index(
                cur,
                "idx_attendance_name_date",
                "CREATE INDEX idx_attendance_name_date ON attendance (name, date)",
            )
            self._ensure_index(
                cur,
                "idx_attendance_open_checkout",
                "CREATE INDEX idx_attendance_open_checkout "
                "ON attendance (name, date, check_out, id)",
            )
            cur.close()

    @staticmethod
    def _ensure_index(cur, index_name: str, create_sql: str) -> None:
        cur.execute("SHOW INDEX FROM attendance WHERE Key_name=%s", (index_name,))
        if cur.fetchone() is None:
            cur.execute(create_sql)

    def check_in(self, name: str) -> int:
        today = date.today().isoformat()
        now = datetime.now().strftime("%H:%M:%S")
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO attendance (name, date, check_in) VALUES (%s, %s, %s)",
                (name, today, now),
            )
            last_id = cur.lastrowid
            cur.close()
            return last_id

    def check_out(self, name: str) -> int | None:
        today = date.today().isoformat()
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, check_in FROM attendance "
                "WHERE name=%s AND date=%s AND check_out IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (name, today),
            )
            row = cur.fetchone()
            if row is None:
                cur.close()
                return None
            row_id, check_in_str = row
            now = datetime.now().strftime("%H:%M:%S")
            t_in = datetime.strptime(check_in_str, "%H:%M:%S")
            t_out = datetime.strptime(now, "%H:%M:%S")
            duration = int((t_out - t_in).total_seconds() / 60)
            cur.execute(
                "UPDATE attendance SET check_out=%s, duration=%s WHERE id=%s",
                (now, duration, row_id),
            )
            cur.close()
            return duration

    def get_today_records(self, name: str) -> list[dict]:
        today = date.today().isoformat()
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, check_in, check_out, duration "
                "FROM attendance WHERE name=%s AND date=%s ORDER BY id",
                (name, today),
            )
            rows = cur.fetchall()
            cur.close()
        return [
            {"id": r[0], "check_in": r[1], "check_out": r[2], "duration": r[3]}
            for r in rows
        ]

    def has_any_record(self, name: str) -> bool:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM attendance WHERE name=%s LIMIT 1", (name,))
            result = cur.fetchone() is not None
            cur.close()
            return result

    def has_record_today(self, name: str, before_now: bool = False) -> bool:
        today = date.today().isoformat()
        if before_now:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM attendance WHERE name=%s AND date<%s LIMIT 1",
                    (name, today),
                )
                result = cur.fetchone() is not None
                cur.close()
                return result
        return bool(self.get_today_records(name))

    def register_employee(self, name: str) -> bool:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    name        VARCHAR(255) NOT NULL UNIQUE,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(
                "INSERT IGNORE INTO employees (name) VALUES (%s)",
                (name,),
            )
            inserted = cur.rowcount > 0
            cur.close()
            return inserted

    def list_employees(self) -> list[str]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    name        VARCHAR(255) NOT NULL UNIQUE,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("SELECT name FROM employees ORDER BY id")
            names = [row[0] for row in cur.fetchall()]
            cur.close()
            return names
