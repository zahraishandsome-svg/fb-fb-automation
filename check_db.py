import sqlite3
con = sqlite3.connect('data/automation.db')
con.row_factory = sqlite3.Row

print('=== Runs today (2026-05-27) ===')
rows = con.execute("SELECT channel_id, slot, status FROM runs WHERE run_date='2026-05-27' ORDER BY slot").fetchall()
for r in rows:
    print(f"  slot {r['slot']} | {r['channel_id']} | {r['status']}")

print()
print('=== Posted videos (page_1) ===')
rows = con.execute("SELECT source_video_id FROM posted_videos WHERE channel_id='page_1'").fetchall()
for r in rows:
    print(f"  {r['source_video_id']}")

con.close()
