"""
Facebook source page: fetch video list and download videos.
Source URLs from the Graph API expire quickly — always download immediately
after fetching, never cache the URL.
"""

import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

_MAX_FETCH_PAGES = 5       # stop after this many API pages (100 videos each)
_DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024   # 8 MB streaming chunks
_MAX_DOWNLOAD_RETRIES = 3


def get_source_videos(
    source_page_id: str,
    access_token: str,
    limit: int = 100,
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch videos from the source Facebook page, newest first.
    Returns a list of video dicts or None on network error.
    Each dict has: id, title, description, created_time, length (seconds).
    Does NOT include the source URL — fetch fresh via get_video_source_url() before downloading.
    """
    videos: List[Dict[str, Any]] = []
    url = f"{GRAPH_URL}/{source_page_id}/videos"
    params = {
        "fields": "id,title,description,created_time,length",
        "access_token": access_token,
        "limit": limit,
    }

    pages_fetched = 0
    while url and pages_fetched < _MAX_FETCH_PAGES:
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch source page videos: %s", exc)
            return None

        data = resp.json()
        batch = data.get("data", [])
        videos.extend(batch)
        logger.debug("Fetched %d videos (page %d)", len(batch), pages_fetched + 1)

        next_page = data.get("paging", {}).get("next")
        url = next_page
        params = {}  # next URL already has all params encoded
        pages_fetched += 1

    videos.reverse()   # oldest first → post chronologically
    return videos


def get_video_source_url(
    video_id: str,
    access_token: str,
) -> Optional[str]:
    """
    Fetch a fresh source URL for a single video.
    Must be called immediately before downloading — FB CDN URLs expire quickly.
    """
    try:
        resp = requests.get(
            f"{GRAPH_URL}/{video_id}",
            params={"fields": "source", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        url = resp.json().get("source")
        if not url:
            logger.error("No source URL returned for video %s", video_id)
        return url
    except requests.RequestException as exc:
        logger.error("Failed to fetch source URL for video %s: %s", video_id, exc)
        return None


def download_video(
    video_id: str,
    source_url: str,
    output_dir: Path,
) -> Optional[Path]:
    """
    Stream-download a video from a FB CDN URL.
    Returns the local path on success, None on failure.
    Call get_video_source_url() immediately before this — URLs expire fast.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.mp4"

    for attempt in range(1, _MAX_DOWNLOAD_RETRIES + 1):
        try:
            with requests.get(source_url, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
            file_size = output_path.stat().st_size
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            logger.info("Downloaded video %s → %.1f MB", video_id, file_size / 1_048_576)
            return output_path
        except Exception as exc:
            logger.warning("Download attempt %d/%d failed for %s: %s",
                           attempt, _MAX_DOWNLOAD_RETRIES, video_id, exc)
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            if attempt < _MAX_DOWNLOAD_RETRIES:
                time.sleep(5 * attempt)

    logger.error("All download attempts failed for video %s", video_id)
    return None


def cleanup_download(video_path: Path) -> None:
    try:
        video_path.unlink(missing_ok=True)
        logger.debug("Cleaned up %s", video_path)
    except OSError as exc:
        logger.warning("Could not delete %s: %s", video_path, exc)


def cleanup_stale_downloads(downloads_dir: Path, max_age_days: int = 7) -> None:
    """Delete downloaded video files older than max_age_days."""
    if not downloads_dir.exists():
        return
    import time as _time
    cutoff = _time.time() - (max_age_days * 86400)
    for mp4 in downloads_dir.rglob("*.mp4"):
        if mp4.stat().st_mtime < cutoff:
            try:
                mp4.unlink()
                logger.debug("Removed stale download: %s", mp4)
            except OSError:
                pass


def is_short_video(length_seconds: Optional[float], max_seconds: int = 180) -> bool:
    """True if the video should be posted as a Reel (short, vertical)."""
    if length_seconds is None:
        return False
    return length_seconds <= max_seconds
