import sqlite3
con = sqlite3.connect('data/automation.db')
con.execute("DELETE FROM posted_videos WHERE channel_id='page_2' AND source_video_id='919766917715129'")
con.execute("DELETE FROM runs WHERE channel_id='page_2'")
con.commit()
rows = con.execute("SELECT COUNT(*) FROM posted_videos WHERE channel_id='page_2'").fetchone()[0]
print("Cleared. Rows remaining for page_2:", rows)
con.close()
