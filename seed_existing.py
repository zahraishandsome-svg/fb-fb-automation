#!/usr/bin/env python3
"""
Seed the DB with source videos that have already been posted to the destination page.
Prevents reposting videos that were manually or previously uploaded.

Matches source videos against destination videos by normalized title.

Usage:
  python seed_existing.py --page page_1
  python seed_existing.py --page page_1 --dry-run   # show matches without writing
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests
from src.config import load_config, load_credentials, load_token
from src.db import init_db, get_connection
from src.fb_source import get_source_videos, GRAPH_URL


def normalize(text: str) -> str:
    """Lowercase, strip emoji, collapse whitespace for fuzzy title matching."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\U0001F600-\U0001F64F]', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_dest_page_videos(page_id: str, token: str) -> list:
    """Fetch existing videos from the destination Facebook Page."""
    videos = []
    url = f"{GRAPH_URL}/{page_id}/videos"
    params = {
        "fields": "id,title,description,created_time",
        "access_token": token,
        "limit": 100,
    }
    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        videos.extend(data.get("data", []))
        next_page = data.get("paging", {}).get("next")
        url = next_page
        params = {}
    return videos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed already-posted source videos into DB to prevent reposts"
    )
    parser.add_argument("--page", required=True, metavar="CHANNEL_ID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show matches without writing to DB")
    args = parser.parse_args()

    config = load_config()
    channels = {ch["id"]: ch for ch in config["channels"]}

    if args.page not in channels:
        print(f"ERROR: Channel '{args.page}' not found in channels.yaml")
        sys.exit(1)

    channel = channels[args.page]
    init_db()

    source_creds = load_credentials(channel["source_credentials_file"])
    source_token_data = load_token(channel["source_token_file"])
    dest_creds = load_credentials(channel["dest_credentials_file"])
    dest_token_data = load_token(channel["dest_token_file"])

    source_page_id = source_creds["page_id"]
    source_token = source_token_data["page_access_token"]
    dest_page_id = dest_creds["page_id"]
    dest_token = dest_token_data["page_access_token"]

    print(f"Fetching existing videos from destination page {dest_page_id}...")
    dest_videos = get_dest_page_videos(dest_page_id, dest_token)
    print(f"  Found {len(dest_videos)} videos on destination page")

    dest_by_title = {normalize(v.get("title") or ""): v for v in dest_videos if v.get("title")}

    print(f"Fetching videos from source page {source_page_id}...")
    source_videos = get_source_videos(source_page_id, source_token)
    if source_videos is None:
        print(f"ERROR: Could not fetch source page {source_page_id} — network or permission error")
        sys.exit(1)
    print(f"  Found {len(source_videos)} videos on source page")

    matched = 0
    conn = get_connection()

    for video in source_videos:
        norm_title = normalize(video.get("title") or "")
        if norm_title in dest_by_title:
            dest_video = dest_by_title[norm_title]
            print(f"  MATCH: '{video.get('title')}' → dest video {dest_video.get('id')}")
            matched += 1

            if not args.dry_run:
                with conn:
                    conn.execute("""
                        INSERT OR IGNORE INTO posted_videos
                            (channel_id, source_video_id, source_title, source_description,
                             source_created_time, dest_video_id, posted_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded')
                    """, (
                        channel["id"],
                        video["id"],
                        video.get("title"),
                        video.get("description"),
                        video.get("created_time"),
                        dest_video.get("id"),
                        dest_video.get("created_time", datetime.utcnow().isoformat()),
                    ))
                    conn.execute("""
                        UPDATE posted_videos
                        SET status = 'uploaded', dest_video_id = ?, posted_at = ?
                        WHERE channel_id = ? AND source_video_id = ? AND status != 'uploaded'
                    """, (
                        dest_video.get("id"),
                        dest_video.get("created_time", datetime.utcnow().isoformat()),
                        channel["id"],
                        video["id"],
                    ))

    conn.close()

    print(f"\nMatched {matched} / {len(source_videos)} source videos to existing dest posts.")
    if args.dry_run:
        print("DRY RUN — no changes written to DB.")
    else:
        print("Seeding complete. These videos will not be reposted.")


if __name__ == "__main__":
    main()
