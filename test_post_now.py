"""
Post one video from a channel RIGHT NOW without consuming a scheduled slot.
- Fetches the most popular unposted video from source page
- Downloads and uploads it to dest page immediately (no scheduled publish time)
- Marks it in posted_videos so the bot never reposts it
- Does NOT touch the runs table — all 3 daily slots remain intact

Usage:
  python test_post_now.py --page page_2
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, load_credentials, load_token
from src.db import init_db, get_connection, get_posted_video_ids, record_video_seen, mark_uploaded
from src.fb_source import get_source_videos, get_video_source_url, download_video, cleanup_download, is_short_video
from src.facebook_poster import upload_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DOWNLOADS_DIR = Path(__file__).parent / "downloads"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True, help="Channel ID e.g. page_2")
    args = parser.parse_args()

    config = load_config()
    channels = {ch["id"]: ch for ch in config["channels"]}

    if args.page not in channels:
        print(f"ERROR: '{args.page}' not found in channels.yaml")
        sys.exit(1)

    channel = channels[args.page]
    channel_id = channel["id"]
    init_db()

    source_creds = load_credentials(channel["source_credentials_file"])
    source_token_data = load_token(channel["source_token_file"])
    dest_creds = load_credentials(channel["dest_credentials_file"])
    dest_token_data = load_token(channel["dest_token_file"])

    source_page_id = source_creds["page_id"]
    source_token = source_token_data["page_access_token"]
    dest_page_id = dest_creds["page_id"]
    dest_token = dest_token_data["page_access_token"]

    print(f"\nFetching videos from {channel['source_page_name']}...")
    videos = get_source_videos(source_page_id, source_token)
    if not videos:
        print("ERROR: No videos found on source page")
        sys.exit(1)

    already_posted = get_posted_video_ids(channel_id)
    unposted = [v for v in videos if v["id"] not in already_posted]

    if not unposted:
        print("No unposted videos available")
        sys.exit(0)

    video = unposted[0]
    views = video.get("views", 0)
    length = video.get("length", 0)
    mins, secs = divmod(int(length or 0), 60)
    duration = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
    print(f"\nSelected: {video['id']} | {views:,} views | {duration} | '{video.get('title', '')}'")

    print("\nFetching source URL...")
    source_url = get_video_source_url(video["id"], source_token)
    if not source_url:
        print("ERROR: Could not get source URL")
        sys.exit(1)

    print("Downloading...")
    channel_dir = DOWNLOADS_DIR / channel_id
    local_file = download_video(video["id"], source_url, channel_dir)
    if not local_file:
        print("ERROR: Download failed")
        sys.exit(1)

    is_reel = is_short_video(
        video.get("length"),
        channel.get("shorts_max_seconds", 180),
        width=video.get("width", 0),
        height=video.get("height", 0),
    )

    title = video.get("title") or video["id"]
    description = video.get("description") or ""

    print(f"\nUploading to {channel['dest_page_name']} (publish immediately)...")
    dest_video_id = upload_video(
        page_id=dest_page_id,
        page_access_token=dest_token,
        video_path=local_file,
        title=title,
        description=description,
        is_reel=is_reel,
        dry_run=False,
        scheduled_publish_time=None,  # publish immediately
    )

    if dest_video_id:
        record_video_seen(channel_id, video)
        mark_uploaded(channel_id, video["id"], dest_video_id)
        cleanup_download(local_file)
        print(f"\nSUCCESS: https://www.facebook.com/video/{dest_video_id}")
        print("Bot will NOT repost this video. All 3 daily slots are still intact.")
    else:
        print("\nERROR: Upload failed")
        cleanup_download(local_file)
        sys.exit(1)


if __name__ == "__main__":
    main()
