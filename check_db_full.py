import sqlite3
con = sqlite3.connect('data/automation.db')
con.row_factory = sqlite3.Row

print("=== ALL runs (last 30) ===")
rows = con.execute("SELECT channel_id, slot, status, run_date FROM runs ORDER BY run_date DESC, slot LIMIT 30").fetchall()
for r in rows:
    print(f"  {r['run_date']} {r['channel_id']} slot {r['slot']} -> {r['status']}")

print()
print("=== posted_videos counts by channel ===")
rows2 = con.execute("SELECT channel_id, status, COUNT(*) as n FROM posted_videos GROUP BY channel_id, status").fetchall()
for r in rows2:
    print(f"  {r['channel_id']} {r['status']}: {r['n']}")

con.close()
