import sqlite3

cookie_path = r'C:\Users\Zahid\AppData\Local\Google\Chrome\User Data\Profile 22\Network\Cookies'
uri = "file:///" + cookie_path.replace("\\", "/") + "?mode=ro&immutable=1"

try:
    conn = sqlite3.connect(uri, uri=True)
    cursor = conn.execute("SELECT name, host_key FROM cookies WHERE host_key LIKE '%facebook%' LIMIT 5")
    rows = cursor.fetchall()
    print(f"SUCCESS — {len(rows)} Facebook cookies found")
    for r in rows:
        print(r)
    conn.close()
except Exception as e:
    print(f"Failed: {e}")
