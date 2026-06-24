"""一键清除: 打卡记录 / 人脸向量 / 员工信息"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("=" * 50)
    print("  数据清除工具")
    print("=" * 50)
    print("  1. 清除所有打卡记录 (MySQL)")
    print("  2. 清除所有员工信息 (MySQL)")
    print("  3. 清除所有向量数据 (pgvector)")
    print("  4. 清除 Redis 签到/签退状态")
    print("  5. 清除全部 (MySQL + pgvector + Redis)")
    print("  0. 退出")
    print("=" * 50)
    print("  支持多选: 输入 1 2 或 1,2")

    raw = input("请选择: ").strip()
    if not raw:
        print("无效输入")
        return

    numbers = raw.replace(",", " ").split()
    for num in numbers:
        if num == "0":
            print("已退出")
            return
        elif num == "1":
            clear_attendance()
        elif num == "2":
            clear_employees()
        elif num == "3":
            clear_vectors()
        elif num == "4":
            clear_redis()
        elif num == "5":
            clear_attendance()
            clear_employees()
            clear_vectors()
            clear_redis()
        else:
            print(f"无效选项: {num}")


def clear_attendance():
    confirm = input("确认清除所有打卡记录? (y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return
    try:
        from core.attendance_db import AttendanceDB

        db = AttendanceDB()
        cur = db._conn.cursor()
        cur.execute("DELETE FROM attendance")
        cur.close()
        print("打卡记录已全部清除")
    except Exception as e:
        print(f"失败: {e}")


def clear_employees():
    confirm = input("确认清除所有员工信息? (y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return
    try:
        from core.attendance_db import AttendanceDB

        db = AttendanceDB()
        cur = db._conn.cursor()
        cur.execute("DELETE FROM employees")
        cur.close()
        print("员工信息已全部清除")
    except Exception as e:
        print(f"失败: {e}")


def clear_vectors():
    confirm = input("确认清除所有向量数据? (y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return
    try:
        from core.vector_db import VectorDB

        db = VectorDB()
        cur = db._conn.cursor()
        cur.execute("DELETE FROM face_embeddings")
        cur.close()
        print("向量数据已全部清除")
    except Exception as e:
        print(f"失败: {e}")


def clear_redis():
    confirm = input("确认清除所有 Redis 签到/签退状态? (y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return
    try:
        from core.redis_checkin import RedisCheckIn

        r = RedisCheckIn()
        if r._r is None:
            print("Redis 不可用, 无需清除")
            return
        deleted = 0
        for pattern in ("checkin:*", "checkout:*"):
            for key in r._r.scan_iter(match=pattern):
                r._r.delete(key)
                deleted += 1
        print(f"Redis 清除完成: {deleted} 个 key")
    except Exception as e:
        print(f"失败: {e}")


if __name__ == "__main__":
    main()
