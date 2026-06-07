"""Patches for gopro_overlay.ffmpeg_gopro.FFMPEGGoPro.

Adds find_timecode() method to extract timecode from video metadata.
This is needed for Final Cut Pro relink functionality.
"""

import json
import logging
import re
from json import JSONDecodeError
from pathlib import Path

logger = logging.getLogger(__name__)

_JSON_BACKSLASH_RUN_RE = re.compile(r"\\+")
_SIMPLE_JSON_ESCAPES = frozenset('"\\/bfnrt')
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _is_valid_json_escape(output: str, escape_index: int) -> bool:
    if escape_index >= len(output):
        return False
    char = output[escape_index]
    if char in _SIMPLE_JSON_ESCAPES:
        return True
    if char != "u":
        return False
    digits = output[escape_index + 1 : escape_index + 5]
    return len(digits) == 4 and all(digit in _HEX_DIGITS for digit in digits)


def _repair_invalid_json_escapes(output: str) -> str:
    def replace(match: re.Match[str]) -> str:
        run = match.group(0)
        if len(run) % 2 == 0:
            return run
        if _is_valid_json_escape(output, match.end()):
            return run
        return run + "\\"

    return _JSON_BACKSLASH_RUN_RE.sub(replace, output)


def loads_ffprobe_json(output: str):
    """Parse ffprobe JSON, tolerating metadata tags with raw Windows backslashes."""
    try:
        return json.loads(output)
    except JSONDecodeError as e:
        if "Invalid \\escape" not in str(e) and "Invalid \\u" not in str(e):
            raise
        fixed_output = _repair_invalid_json_escapes(output)
        return json.loads(fixed_output)


def _patch_ffmpeg_gopro_json_loader() -> None:
    """Make gopro_overlay.ffmpeg_gopro use a lenient JSON loader for ffprobe output."""
    import gopro_overlay.ffmpeg_gopro as ffmpeg_gopro_module

    current_json = getattr(ffmpeg_gopro_module, "json", None)
    if getattr(current_json, "_gpstitch_lenient_ffprobe_json", False):
        return

    class _JsonProxy:
        _gpstitch_lenient_ffprobe_json = True

        @staticmethod
        def loads(output: str):
            return loads_ffprobe_json(output)

    ffmpeg_gopro_module.json = _JsonProxy()
    logger.debug("Patched FFMPEGGoPro ffprobe JSON loader")


def patch_ffmpeg_gopro() -> None:
    """Add find_timecode method to FFMPEGGoPro class."""
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

    _patch_ffmpeg_gopro_json_loader()

    # Check if already patched
    if hasattr(FFMPEGGoPro, "find_timecode"):
        logger.debug("FFMPEGGoPro.find_timecode already exists, skipping patch")
        return

    def find_timecode(self, filepath: Path) -> str | None:
        """Extract timecode from video file metadata using ffprobe.

        This timecode is important for Final Cut Pro compatibility,
        allowing proper relinking of the processed video.

        Args:
            filepath: Path to video file

        Returns:
            Timecode string (HH:MM:SS:FF) if found, None otherwise
        """
        try:
            ffprobe_output = str(
                self.exe.ffprobe()
                .invoke(
                    [
                        "-hide_banner",
                        "-print_format",
                        "json",
                        "-show_streams",
                        "-select_streams",
                        "v:0",
                        filepath,
                    ]
                )
                .stdout
            )

            ffprobe_json = loads_ffprobe_json(ffprobe_output)
            streams = ffprobe_json.get("streams", [])

            if streams:
                tags = streams[0].get("tags", {})
                timecode = tags.get("timecode")
                if timecode:
                    logger.debug(f"Found timecode in {filepath}: {timecode}")
                    return timecode

        except Exception as e:
            logger.warning(f"Failed to extract timecode from {filepath}: {e}")

        return None

    # Apply the patch
    FFMPEGGoPro.find_timecode = find_timecode
    logger.debug("Patched FFMPEGGoPro with find_timecode method")
