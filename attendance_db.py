"""考勤数据库: MySQL 记录上下班打卡时间及工作时长"""

import logging
from datetime import date, datetime

import pymysql

from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
    MYSQL_CHARSET,
)

logger = logging.getLogger(__name__)


class AttendanceDB:
    def __init__(self):
        self._conn = self._create_conn()
        self._ensure_database(self._conn)
        self._conn.select_db(MYSQL_DATABASE)
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

    def _ensure_database(self, conn):
        cur = conn.cursor()
        cur.execute(
            "CREATE DATABASE IF NOT EXISTS `%s`"
            " DEFAULT CHARACTER SET utf8mb4"
            " DEFAULT COLLATE utf8mb4_unicode_ci" % MYSQL_DATABASE
        )
        cur.close()

    def _ensure_conn(self):
        """断线重连: 长时间运行的摄像头程序可能因 MySQL wait_timeout 断开连接。"""
        try:
            self._conn.ping(reconnect=True)
        except Exception:
            self._conn = self._create_conn(database=MYSQL_DATABASE)

    def _init_table(self):
        cur = self._conn.cursor()
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
        cur.close()

    def check_in(self, name: str) -> int:
        """上班打卡, 返回记录 ID"""
        self._ensure_conn()
        today = date.today().isoformat()
        now = datetime.now().strftime("%H:%M:%S")
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO attendance (name, date, check_in) VALUES (%s, %s, %s)",
            (name, today, now),
        )
        last_id = cur.lastrowid
        cur.close()
        return last_id

    def check_out(self, name: str) -> int | None:
        """
        下班打卡: 找到此人今天最近一次未签退的记录, 写入签退时间和时长(分钟)。
        返回工作时长(分钟), 若无未签退记录返回 None。
        """
        self._ensure_conn()
        today = date.today().isoformat()
        cur = self._conn.cursor()
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
        """查询某人今日所有打卡记录"""
        self._ensure_conn()
        today = date.today().isoformat()
        cur = self._conn.cursor()
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
