"""Tests for NVIDIA FFmpeg profile patches."""


def test_nvgpu_profiles_are_cuda_nvenc_compatible():
    from gpstitch.patches import apply_patches
    from gopro_overlay.ffmpeg_profile import builtin_profiles

    apply_patches()

    nvgpu = builtin_profiles["nvgpu"]
    nnvgpu = builtin_profiles["nnvgpu"]

    assert nvgpu["input"] == ["-hwaccel", "cuda"]
    assert "h264_nvenc" in nvgpu["output"]
    assert nnvgpu["input"] == ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    assert "overlay_cuda" in nnvgpu["filter"]
    assert "hwupload_cuda[overlay_stream]" in nnvgpu["filter"]
    assert "hwupload[overlay_stream]" not in nnvgpu["filter"]
    assert "h264_nvenc" in nnvgpu["output"]
