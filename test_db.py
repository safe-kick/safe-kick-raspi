from app.db import get_connection

conn = get_connection()
cursor = conn.cursor()

print("===== sessions =====")

cursor.execute("SELECT * FROM sessions")
for row in cursor.fetchall():
    print(dict(row))

print("\n===== sensor_logs =====")

cursor.execute("SELECT * FROM sensor_logs")
for row in cursor.fetchall():
    print(dict(row))

print("\n===== warning_logs =====")

cursor.execute("SELECT * FROM warning_logs")
for row in cursor.fetchall():
    print(dict(row))

conn.close()