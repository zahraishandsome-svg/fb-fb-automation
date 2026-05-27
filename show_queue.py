"""Show exactly which videos the bot will pick for today's 3 slots."""
import json, sqlite3
from pathlib import Path
from src.fb_source import get_source_videos

ROOT = Path(__file__).parent

src_creds = json.loads((ROOT / "credentials/page_1_source_credentials.json").read_text())
src_token = json.loads((ROOT / "tokens/page_1_source_token.json").read_text())

con = sqlite3.connect("data/automation.db")
con.row_factory = sqlite3.Row
posted_ids = {r[0] for r in con.execute(
    "SELECT source_video_id FROM posted_videos WHERE channel_id='page_1' AND status IN ('uploaded','failed_permanent','skipped')"
).fetchall()}
con.close()

print(f"Already posted: {len(posted_ids)} videos")
print("Fetching all videos from Walter Hayes (sorted by views — most popular first)...")

videos = get_source_videos(src_creds["page_id"], src_token["page_access_token"])
print(f"Total videos fetched: {len(videos)}")

unposted = [v for v in videos if v["id"] not in posted_ids]
print(f"Unposted: {len(unposted)}\n")

print("Next 3 videos the bot will pick (Slot 1, 2, 3):")
for i, v in enumerate(unposted[:3], 1):
    length = v.get("length", 0)
    mins, secs = divmod(int(length or 0), 60)
    duration = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
    orient = "Portrait/Reel" if v.get("height", 0) > v.get("width", 0) else "Landscape"
    views = v.get("views", 0)
    likes = v.get("likes", 0)
    print(f"  Slot {i}: {v['id']} | {views:,} views | {likes:,} likes | {duration} | {orient} | created {str(v.get('created_time','?'))[:10]}")
