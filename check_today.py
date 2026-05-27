import sqlite3
from datetime import date

con = sqlite3.connect('data/automation.db')
con.row_factory = sqlite3.Row
today = str(date.today())

print("=== Runs today ===")
rows = con.execute("SELECT channel_id, slot, status, run_date FROM runs WHERE run_date=?", (today,)).fetchall()
for r in rows:
    print(f"  {r['channel_id']} slot {r['slot']} -> {r['status']}")
if not rows:
    print("  (none — all 3 slots still open for both pages)")

print()
print("=== posted_videos page_2 ===")
rows2 = con.execute("SELECT source_video_id, status FROM posted_videos WHERE channel_id='page_2'").fetchall()
for r in rows2:
    print(f"  {r['source_video_id']} -> {r['status']}")
if not rows2:
    print("  (none)")

print()
print("=== posted_videos page_1 count ===")
count = con.execute("SELECT COUNT(*) FROM posted_videos WHERE channel_id='page_1'").fetchone()[0]
print(f"  {count} videos already posted")

con.close()
