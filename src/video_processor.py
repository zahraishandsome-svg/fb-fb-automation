"""
Re-encode a video using ffmpeg to change its binary fingerprint.

Used to avoid Facebook's duplicate content detection when cross-posting
videos that already exist on another Facebook page. FB fingerprints video
streams — re-encoding with different GOP structure and compression
parameters produces a new signature that isn't matched to the source.

Visual quality is preserved (CRF 23 is near-transparent quality loss).
"""

import subprocess
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def is_ffmpeg_available() -> bool:
    """Return True if ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def reencode_video(input_path: Path, output_path: Path) -> Path:
    """
    Re-encode a video with ffmpeg to change its fingerprint.

    Args:
        input_path:  Path to original downloaded video.
        output_path: Desired output path for the re-encoded video.

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: if ffmpeg is not on PATH.
        RuntimeError:      if ffmpeg exits with non-zero code or times out.
    """
    if not is_ffmpeg_available():
        raise FileNotFoundError(
            "ffmpeg not found on PATH. "
            "Add the 'Install ffmpeg' step to the workflow."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c:v", "libx264",
        "-crf", "23",              # near-lossless quality
        "-preset", "fast",         # fast enough for CI runners
        "-c:a", "aac",
        "-ar", "44100",            # standard audio sample rate
        "-movflags", "+faststart", # web-optimised MP4 atom ordering
        str(output_path),
    ]

    logger.info("[processor] Re-encoding %s → %s", input_path.name, output_path.name)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10-min cap — large videos on slow runners
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ffmpeg re-encode timed out (>10 min) for {input_path.name}"
        )

    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-2000:]
        logger.error(
            "[processor] ffmpeg failed (code %d):\n%s",
            result.returncode, stderr_tail,
        )
        raise RuntimeError(
            f"ffmpeg re-encode failed for {input_path.name} "
            f"(exit code {result.returncode})"
        )

    size_mb = output_path.stat().st_size / 1_048_576
    logger.info("[processor] Done: %s (%.1f MB)", output_path.name, size_mb)
    return output_path
