import sqlite3
con = sqlite3.connect('data/automation.db')
con.execute("DELETE FROM posted_videos WHERE channel_id='page_1' AND source_video_id='1564235085266506'")
con.commit()
print("Removed test video from DB. Bot will pick it normally when its turn comes.")
con.close()
