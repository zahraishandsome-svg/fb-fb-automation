"""
Test that video_state=SCHEDULED works for Reels.
Uses the 4th queued video from page_1 (not today's slot 1/2/3 videos).
Schedules it 20 minutes from now.
Marks it in DB so bot won't pick it again.
"""
import sys, logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from src.config import load_config, load_credentials, load_token
from src.fb_source import get_source_videos, get_video_source_url, download_video, cleanup_download, is_short_video
from src.facebook_poster import upload_video
from src.db import init_db, get_posted_video_ids, record_video_seen, mark_uploaded

DOWNLOADS_DIR = Path(__file__).parent / "downloads"

cfg = load_config()
ch = next(c for c in cfg['channels'] if c['id'] == 'page_1')
init_db()

src_creds = load_credentials(ch['source_credentials_file'])
src_token = load_token(ch['source_token_file'])
dest_creds = load_credentials(ch['dest_credentials_file'])
dest_token = load_token(ch['dest_token_file'])

videos = get_source_videos(src_creds['page_id'], src_token['page_access_token'])
posted = get_posted_video_ids('page_1')
unposted = [v for v in videos if v['id'] not in posted]

# Use the 4th video — slots 1/2/3 use positions 0/1/2, this won't interfere
video = unposted[3]
print(f"\nTest video: {video['id']} | {video.get('views',0):,} views | {int(video.get('length') or 0)}s")

source_url = get_video_source_url(video['id'], src_token['page_access_token'])
local_file = download_video(video['id'], source_url, DOWNLOADS_DIR / 'page_1')
print(f"Downloaded: {local_file}")

# Schedule 20 minutes from now
scheduled_time = int((datetime.now(timezone.utc) + timedelta(minutes=20)).timestamp())
print(f"Scheduling for: {datetime.utcfromtimestamp(scheduled_time).strftime('%H:%M UTC')} (20 min from now)")

dest_video_id = upload_video(
    page_id=dest_creds['page_id'],
    page_access_token=dest_token['page_access_token'],
    video_path=local_file,
    title=video.get('title') or video['id'],
    description=video.get('description') or '',
    is_reel=True,
    dry_run=False,
    scheduled_publish_time=scheduled_time,
)

if dest_video_id:
    record_video_seen('page_1', video)
    mark_uploaded('page_1', video['id'], dest_video_id)
    cleanup_download(local_file)
    print(f"\nSUCCESS — video_state=SCHEDULED works!")
    print(f"Scheduled video: https://www.facebook.com/video/{dest_video_id}")
    print("Today's slots 1/2/3 unaffected.")
else:
    cleanup_download(local_file)
    print(f"\nFAILED — video_state=SCHEDULED does NOT work. Need to revert to published=false")
    sys.exit(1)
