"""查看考勤数据库记录"""

import pymysql

from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
    MYSQL_CHARSET,
)

conn = pymysql.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
    charset=MYSQL_CHARSET,
    cursorclass=pymysql.cursors.Cursor,
)
cur = conn.cursor()
cur.execute(
    "SELECT id, name, date, check_in, check_out, duration "
    "FROM attendance ORDER BY id DESC LIMIT 50"
)
rows = cur.fetchall()

print(
    f"\n{'ID':<5} {'姓名':<10} {'日期':<12} {'上班':<10} {'下班':<10} {'时长(分钟)':<12}"
)
print("-" * 65)
for r in rows:
    rid, name, dt, cin, cout, dur = r
    cout = cout or "----"
    dur = f"{dur}" if dur else "----"
    print(f"{rid:<5} {name:<10} {dt:<12} {cin:<10} {cout:<10} {dur:<12}")

print(f"\n共 {len(rows)} 条记录")
cur.close()
conn.close()
