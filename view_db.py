"""查看考勤数据库记录"""

import sqlite3
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "cache", "attendance.db")

if not os.path.exists(DB_FILE):
    print("数据库文件不存在，请先运行 app.py 产生打卡记录。")
    exit()

conn = sqlite3.connect(DB_FILE)
cur = conn.execute("SELECT id, name, date, check_in, check_out, duration FROM attendance ORDER BY id DESC LIMIT 50")
rows = cur.fetchall()

print(f"\n{'ID':<5} {'姓名':<10} {'日期':<12} {'上班':<10} {'下班':<10} {'时长(分钟)':<12}")
print("-" * 65)
for r in rows:
    rid, name, dt, cin, cout, dur = r
    cout = cout or "----"
    dur = f"{dur}" if dur else "----"
    print(f"{rid:<5} {name:<10} {dt:<12} {cin:<10} {cout:<10} {dur:<12}")

print(f"\n共 {len(rows)} 条记录")
conn.close()
