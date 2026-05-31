"""Tests for NVIDIA FFmpeg profile patches."""


def _option_value(options: list[str], option: str) -> str | None:
    if option not in options:
        return None
    idx = options.index(option)
    if idx + 1 >= len(options):
        return None
    return options[idx + 1]


def test_nvgpu_profile_uses_cuda_hwaccel_and_nvenc():
    from gpstitch.patches import apply_patches
    from gopro_overlay.ffmpeg_profile import builtin_profiles

    apply_patches()

    nvgpu = builtin_profiles["nvgpu"]

    assert nvgpu["input"] == ["-hwaccel", "cuda"]
    assert "nvdec" not in nvgpu["input"]
    assert _option_value(nvgpu["output"], "-vcodec") == "h264_nvenc"
    assert _option_value(nvgpu["output"], "-profile:v") == "high"


def test_nnvgpu_profile_uses_cuda_overlay_upload_and_nvenc():
    from gpstitch.patches import apply_patches
    from gopro_overlay.ffmpeg_profile import builtin_profiles

    apply_patches()

    nnvgpu = builtin_profiles["nnvgpu"]

    assert nnvgpu["input"] == ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    assert "overlay_cuda" in nnvgpu["filter"]
    assert "hwupload_cuda[overlay_stream]" in nnvgpu["filter"]
    assert "hwupload[overlay_stream]" not in nnvgpu["filter"]
    assert _option_value(nnvgpu["output"], "-vcodec") == "h264_nvenc"
    assert _option_value(nnvgpu["output"], "-profile:v") == "main"
