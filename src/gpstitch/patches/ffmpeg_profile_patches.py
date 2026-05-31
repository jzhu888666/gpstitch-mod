"""Patch FFmpeg profile definitions used by gopro_overlay."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def patch_ffmpeg_profiles() -> None:
    """Ensure NVIDIA GPU profiles use CUDA/NVENC-compatible settings."""
    from gopro_overlay.ffmpeg_profile import builtin_profiles

    nvgpu = builtin_profiles.get("nvgpu")
    if nvgpu is not None:
        nvgpu["input"] = ["-hwaccel", "cuda"]
        _ensure_nvenc_output(nvgpu, h264_profile="high")

    nnvgpu = builtin_profiles.get("nnvgpu")
    if nnvgpu is not None:
        nnvgpu["input"] = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        nnvgpu["filter"] = (
            "[0:v]scale_cuda=format=yuv420p[mp4_stream];"
            "[1:v]format=yuva420p,hwupload_cuda[overlay_stream];"
            "[mp4_stream][overlay_stream]overlay_cuda"
        )
        _ensure_nvenc_output(nnvgpu, h264_profile="main")

    logger.debug("Patched NVIDIA FFmpeg profiles for CUDA/NVENC")


def _ensure_nvenc_output(profile_data: dict, h264_profile: str) -> None:
    output = list(profile_data.get("output") or [])
    if "-vcodec" in output:
        idx = output.index("-vcodec")
        if idx + 1 < len(output):
            output[idx + 1] = "h264_nvenc"
    else:
        output = ["-vcodec", "h264_nvenc", *output]

    if "-profile:v" in output:
        idx = output.index("-profile:v")
        if idx + 1 < len(output):
            output[idx + 1] = h264_profile
    else:
        output.extend(["-profile:v", h264_profile])

    profile_data["output"] = output
