"""
Runs the full FB→Facebook pipeline for a single channel, one slot.
Called by orchestrator.py — never runs all channels directly.
Returns a result dict so orchestrator can aggregate and notify.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from . import db
from .config import load_credentials, load_token
from .fb_source import (
    get_source_videos, get_video_source_url, download_video,
    cleanup_download, cleanup_stale_downloads, is_short_video,
)
from .facebook_poster import (
    upload_video, check_token_expiry, TOKEN_EXPIRY_WARNING_DAYS,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"


def run_channel(channel: Dict[str, Any], slot: int, dry_run: bool = False) -> Dict[str, Any]:
    """
    Full pipeline for one channel, one slot.
    Returns: {channel_id, slot, status, video_uploaded, fb_url, error, token_warnings}
    Never raises.
    """
    channel_id = channel["id"]
    result = {
        "channel_id": channel_id,
        "slot": slot,
        "status": "skipped",
        "video_uploaded": None,
        "fb_url": None,
        "error": None,
        "token_warning": None,
    }

    run_id = db.start_run(channel_id, slot)

    try:
        if db.slot_already_ran(channel_id, slot):
            logger.info("[%s] Slot %d already ran today — skipping", channel_id, slot)
            db.finish_run(run_id, "skipped")
            return result

        db.upsert_channel(channel)
        cleanup_stale_downloads(DOWNLOADS_DIR, max_age_days=7)

        # Load credentials and tokens
        try:
            source_creds = load_credentials(channel["source_credentials_file"])
            source_token_data = load_token(channel["source_token_file"])
            dest_creds = load_credentials(channel["dest_credentials_file"])
            dest_token_data = load_token(channel["dest_token_file"])
        except FileNotFoundError as exc:
            error_msg = str(exc)
            logger.error("[%s] %s", channel_id, error_msg)
            db.finish_run(run_id, "failed", error_message=error_msg)
            result["status"] = "failed"
            result["error"] = error_msg
            return result

        # Token expiry checks
        token_warnings = []

        src_expired, src_days_left = check_token_expiry(source_token_data)
        if src_expired:
            error_msg = (
                f"Source page token is expired. Run: "
                f"python refresh_source_token.py --page {channel_id}"
            )
            logger.error("[%s] %s", channel_id, error_msg)
            db.finish_run(run_id, "failed", error_message=error_msg)
            result["status"] = "failed"
            result["error"] = error_msg
            return result
        if src_days_left <= TOKEN_EXPIRY_WARNING_DAYS:
            warn = (
                f"Source token expires in {src_days_left} days. Run: "
                f"python refresh_source_token.py --page {channel_id}"
            )
            logger.warning("[%s] %s", channel_id, warn)
            token_warnings.append(warn)

        dest_expired, dest_days_left = check_token_expiry(dest_token_data)
        if dest_expired:
            error_msg = (
                f"Dest page token is expired. Run: "
                f"python refresh_token.py --page {channel_id}"
            )
            logger.error("[%s] %s", channel_id, error_msg)
            db.finish_run(run_id, "failed", error_message=error_msg)
            result["status"] = "failed"
            result["error"] = error_msg
            return result
        if dest_days_left <= TOKEN_EXPIRY_WARNING_DAYS:
            warn = (
                f"Dest token expires in {dest_days_left} days. Run: "
                f"python refresh_token.py --page {channel_id}"
            )
            logger.warning("[%s] %s", channel_id, warn)
            token_warnings.append(warn)

        if token_warnings:
            result["token_warning"] = " | ".join(token_warnings)

        source_page_id = source_creds["page_id"]
        source_token = source_token_data["page_access_token"]
        dest_page_id = dest_creds["page_id"]
        dest_token = dest_token_data["page_access_token"]

        # Pick one video to upload this slot
        video, is_retry = _pick_next_video(channel, source_page_id, source_token)
        if video is None:
            logger.info("[%s] No unposted videos available for slot %d", channel_id, slot)
            db.finish_run(run_id, "no_content")
            result["status"] = "no_content"
            return result

        logger.info("[%s] Selected video: %s | '%s'", channel_id, video["id"], video.get("title", ""))

        # Get fresh source URL immediately before download (FB URLs expire fast)
        local_file = _download_video(channel, video, source_token, dry_run)
        if local_file is None:
            _handle_failure(channel, video, "Download failed after retries")
            db.finish_run(run_id, "failed", error_message="Download failed")
            result["status"] = "failed"
            result["error"] = "Download failed"
            return result

        length_seconds = video.get("length")
        is_reel = is_short_video(length_seconds, channel.get("shorts_max_seconds", 180))

        title = video.get("title") or video["id"]
        description = _build_description(video, channel)

        # Compute scheduled publish time from per-channel slot_publish_times_utc config
        scheduled_publish_time: Optional[int] = _get_scheduled_publish_time(channel, slot, channel_id)

        dest_video_id = upload_video(
            page_id=dest_page_id,
            page_access_token=dest_token,
            video_path=local_file,
            title=title,
            description=description,
            is_reel=is_reel,
            dry_run=dry_run,
            scheduled_publish_time=scheduled_publish_time,
        )

        if dest_video_id:
            if not dry_run:
                db.mark_uploaded(channel_id, video["id"], dest_video_id)
                db.finish_run(run_id, "success", videos_uploaded=1)
            else:
                db.finish_run(run_id, "dry_run", videos_uploaded=0)
                logger.info("[%s] [DRY RUN] Would have uploaded: https://www.facebook.com/video/%s",
                            channel_id, dest_video_id)
            cleanup_download(local_file)
            result["status"] = "success"
            result["video_uploaded"] = title
            result["fb_url"] = f"https://www.facebook.com/video/{dest_video_id}"
            if not dry_run:
                logger.info("[%s] Uploaded: %s", channel_id, result["fb_url"])
        else:
            _handle_failure(channel, video, "Upload returned no video ID")
            db.finish_run(run_id, "failed", error_message="Upload failed")
            result["status"] = "failed"
            result["error"] = "Upload returned no video ID"

    except Exception as exc:
        error_msg = f"Unexpected error: {exc}"
        logger.exception("[%s] %s", channel_id, error_msg)
        db.finish_run(run_id, "failed", error_message=error_msg)
        result["status"] = "failed"
        result["error"] = error_msg

    return result


# ── Video selection ───────────────────────────────────────────────────────────

def _pick_next_video(
    channel: Dict[str, Any],
    source_page_id: str,
    source_token: str,
) -> tuple[Optional[Dict[str, Any]], bool]:
    """
    Returns (video_dict, is_retry).
    Retry videos take priority over new videos.
    """
    channel_id = channel["id"]
    today = date.today()

    retries = db.get_videos_for_retry(channel_id, today)
    if retries:
        logger.info("[%s] Found %d video(s) due for retry", channel_id, len(retries))
        row = retries[0]
        return {
            "id": row["source_video_id"],
            "title": row["source_title"],
            "description": row["source_description"],
            "created_time": row["source_created_time"],
            "length": None,
        }, True

    videos = get_source_videos(source_page_id, source_token)
    if videos is None:
        raise RuntimeError(
            f"Source FB page {source_page_id} is unreachable — network or permission error"
        )
    if not videos:
        return None, False

    already_posted = db.get_posted_video_ids(channel_id)

    for video in videos:
        if video["id"] not in already_posted:
            db.record_video_seen(channel_id, video)
            return video, False

    return None, False


# ── Download ──────────────────────────────────────────────────────────────────

def _download_video(
    channel: Dict[str, Any],
    video: Dict[str, Any],
    source_token: str,
    dry_run: bool,
) -> Optional[Path]:
    if dry_run:
        logger.info("[DRY RUN] Skipping download for %s", video["id"])
        return DOWNLOADS_DIR / channel["id"] / f"{video['id']}.mp4"

    # Fetch fresh URL immediately before download — FB CDN URLs expire quickly
    source_url = get_video_source_url(video["id"], source_token)
    if not source_url:
        logger.error("[%s] Could not get source URL for video %s", channel["id"], video["id"])
        return None

    channel_dir = DOWNLOADS_DIR / channel["id"]
    return download_video(
        video_id=video["id"],
        source_url=source_url,
        output_dir=channel_dir,
    )


def _handle_failure(channel: Dict[str, Any], video: Dict[str, Any], error_msg: str) -> None:
    today = date.today()
    db.mark_retry(
        channel_id=channel["id"],
        source_video_id=video["id"],
        error_message=error_msg,
        next_retry_date=today + timedelta(days=1),
        max_retries=channel.get("max_retry_days", 3),
    )
    logger.warning("[%s] Video %s queued for retry tomorrow: %s",
                   channel["id"], video["id"], error_msg)


# ── Scheduled publish time ────────────────────────────────────────────────────

def _get_scheduled_publish_time(channel: Dict[str, Any], slot: int,
                                 channel_id: str) -> Optional[int]:
    """
    Calculate the UTC Unix timestamp at which this slot's video should go live.
    Reads slot_publish_times_utc from channel config (e.g. {1: "13:00", 2: "15:00"}).
    Returns a Unix timestamp when the target time is more than 15 minutes in the future —
    video uploads as a draft and Facebook publishes it at exactly that time.
    Returns None if no publish time is configured or the target is already too close/past
    (falls back to immediate publish).
    Facebook requires scheduled_publish_time to be at least 10 minutes in the future.
    """
    times = channel.get("slot_publish_times_utc") or {}
    time_str = times.get(slot) or times.get(str(slot))
    if not time_str:
        return None

    try:
        h, m = map(int, str(time_str).split(":"))
    except (ValueError, AttributeError):
        logger.warning("[%s] Invalid slot_publish_times_utc value: %r", channel_id, time_str)
        return None

    now_utc = datetime.now(timezone.utc)
    target = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
    delta_seconds = (target - now_utc).total_seconds()

    if delta_seconds < 900:   # less than 15 min away or already past → publish immediately
        logger.info(
            "[%s] Slot %d target publish time %02d:%02dZ is past or too close "
            "(%.0f s) — publishing immediately",
            channel_id, slot, h, m, delta_seconds,
        )
        return None

    ts = int(target.timestamp())
    logger.info(
        "[%s] Slot %d scheduling publish at %s (%d min from now)",
        channel_id, slot, target.strftime("%Y-%m-%dT%H:%M:%SZ"), int(delta_seconds / 60),
    )
    return ts


# ── Description ───────────────────────────────────────────────────────────────

def _build_description(video: Dict[str, Any], channel: Dict[str, Any]) -> str:
    parts = [video.get("description") or ""]
    footer = channel.get("description_footer", "")
    if footer:
        parts.append(footer)
    return "\n\n".join(p for p in parts if p).strip()
