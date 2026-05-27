import sqlite3
con = sqlite3.connect('data/automation.db')
# Remove the retry entry for the video we just failed on
con.execute("DELETE FROM video_queue WHERE channel_id='page_1' AND source_video_id='2011779946432549'")
# Also remove today's slot 6 run so it can re-run
con.execute("DELETE FROM runs WHERE channel_id='page_1' AND slot=6 AND run_date='2026-05-27'")
con.commit()
con.close()
print("Cleared retry + slot 6 run record. Ready to re-run.")
