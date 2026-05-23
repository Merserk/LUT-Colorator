"""Merge-mode rendering: apply .cube LUTs to images and videos with FFmpeg."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from lut_common import ensure_dir, find_ffmpeg, project_path, resolve_upload_path, run_hidden, timestamp

CODEC_SETTINGS = {
    "H.264 - Good (MP4)": {
        "vcodec": {False: "libx264", True: "h264_nvenc"},
        "preset": {False: "medium", True: "p4"},
        "crf": "23",
        "nvenc_bitrate": "20000k",
        "ext": ".mp4",
        "extra": ["-pix_fmt", "yuv420p"],
    },
    "H.264 - Best (MP4)": {
        "vcodec": {False: "libx264", True: "h264_nvenc"},
        "preset": {False: "slow", True: "p7"},
        "crf": "18",
        "nvenc_bitrate": "20000k",
        "ext": ".mp4",
        "extra": ["-pix_fmt", "yuv420p"],
    },
    "H.265 - Good (MKV)": {
        "vcodec": {False: "libx265", True: "hevc_nvenc"},
        "preset": {False: "medium", True: "p4"},
        "crf": "25",
        "nvenc_bitrate": "20000k",
        "ext": ".mkv",
        "extra": ["-pix_fmt", "yuv420p"],
    },
    "H.265 - Best (MKV)": {
        "vcodec": {False: "libx265", True: "hevc_nvenc"},
        "preset": {False: "slow", True: "p7"},
        "crf": "20",
        "nvenc_bitrate": "20000k",
        "ext": ".mkv",
        "extra": ["-pix_fmt", "yuv420p"],
    },
    "ProRes 422 Proxy (MOV)": {
        "vcodec": {False: "prores_ks", True: "prores_ks"},
        "profile": "0",
        "ext": ".mov",
        "extra": ["-pix_fmt", "yuv422p10le"],
    },
    "ProRes 422 HQ (MOV)": {
        "vcodec": {False: "prores_ks", True: "prores_ks"},
        "profile": "3",
        "ext": ".mov",
        "extra": ["-pix_fmt", "yuv422p10le"],
    },
    "ProRes 4444 XQ (MOV)": {
        "vcodec": {False: "prores_ks", True: "prores_ks"},
        "profile": "5",
        "ext": ".mov",
        "extra": ["-pix_fmt", "yuva444p10le"],
    },
    "FFV1 Lossless (MKV)": {
        "vcodec": {False: "ffv1", True: "ffv1"},
        "level": "3",
        "ext": ".mkv",
        "extra": ["-pix_fmt", "yuv444p10le", "-coder", "1", "-context", "1", "-slicecrc", "1"],
    },
}

CODEC_OPTIONS = list(CODEC_SETTINGS.keys())
NVENC_CODECS = {"h264_nvenc", "hevc_nvenc"}


class MergeModeEngine:
    """Apply LUT files to videos and still images using FFmpeg."""

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or find_ffmpeg()

    @staticmethod
    def get_codec_settings(codec_name: str, use_nvenc: bool = False) -> dict[str, Any]:
        """Normalize codec settings for the selected codec and acceleration mode."""
        raw = CODEC_SETTINGS.get(codec_name, CODEC_SETTINGS[CODEC_OPTIONS[0]])
        codec = dict(raw)
        codec["vcodec"] = raw["vcodec"][bool(use_nvenc)]
        if "preset" in raw:
            codec["preset"] = raw["preset"][bool(use_nvenc)]
        return codec

    @staticmethod
    def _validate_input(path: str | None, label: str) -> tuple[bool, str]:
        if not path:
            return False, f"Please provide {label}."
        if not Path(path).exists():
            return False, f"{label.capitalize()} not found: {path}"
        return True, ""

    @staticmethod
    def _prepare_local_lut(lut_path: str, ts: int) -> tuple[Path, str]:
        """Copy LUT under output/temp_luts so FFmpeg lut3d path escaping stays simple."""
        luts_dir = ensure_dir(project_path("output", "temp_luts"))
        local_lut_path = luts_dir / f"{ts}_{Path(lut_path).name}"
        shutil.copy2(lut_path, local_lut_path)
        ffmpeg_filter_path = f"output/temp_luts/{local_lut_path.name}".replace("\\", "/")
        return local_lut_path, ffmpeg_filter_path

    def render_video(self, input_video: Any, lut_file: Any, codec_name: str, use_nvenc: bool = False) -> tuple[str | None, str]:
        """Apply LUT to a video and render with the selected codec."""
        input_path = resolve_upload_path(input_video)
        lut_path = resolve_upload_path(lut_file)

        ok, message = self._validate_input(input_path, "input video")
        if not ok:
            return None, message
        ok, message = self._validate_input(lut_path, "LUT file")
        if not ok:
            return None, message

        ts = timestamp()
        codec = self.get_codec_settings(codec_name, use_nvenc)
        base_name = Path(input_path).stem
        output_path = project_path("output", "merge_mode", f"{base_name}_LUT_{ts}{codec['ext']}")
        ensure_dir(output_path.parent)

        local_lut_path, lut_filter_path = self._prepare_local_lut(lut_path, ts)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-threads",
            "0",
            "-i",
            input_path,
            "-c:v",
            codec["vcodec"],
        ]

        if codec["vcodec"] in NVENC_CODECS:
            cmd.extend(["-b_ref_mode", "0", "-b:v", codec.get("nvenc_bitrate", "20000k")])
        elif codec.get("crf"):
            cmd.extend(["-crf", codec["crf"]])

        if codec.get("preset"):
            cmd.extend(["-preset", codec["preset"]])
        if codec.get("profile"):
            cmd.extend(["-profile:v", codec["profile"]])
        if codec.get("level"):
            cmd.extend(["-level", codec["level"]])

        cmd.extend(["-filter_complex", f"[0:v]lut3d=file={lut_filter_path}[out]", "-map", "[out]"])
        cmd.extend(["-c:a", "copy", "-map", "a?"])
        cmd.extend(codec.get("extra", []))
        cmd.extend(["-sws_flags", "spline", "-y", str(output_path)])

        try:
            result = run_hidden(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                nvenc_status = " (NVENC)" if codec["vcodec"] in NVENC_CODECS else ""
                return str(output_path), f"Render complete!{nvenc_status}\nOutput: {output_path.name}"
            error = (result.stderr or "Unknown error")[:1000]
            return None, f"Render failed:\n{error}"
        except FileNotFoundError:
            return None, "FFmpeg not found. Please install FFmpeg or run install.bat."
        except Exception as exc:
            return None, f"Error: {exc}"
        finally:
            try:
                local_lut_path.unlink(missing_ok=True)
            except Exception:
                pass

    def render_image(self, input_image: Any, lut_file: Any, output_format: str = "PNG") -> tuple[str | None, str]:
        """Apply LUT to a still image using FFmpeg."""
        input_path = resolve_upload_path(input_image)
        lut_path = resolve_upload_path(lut_file)

        ok, message = self._validate_input(input_path, "input image")
        if not ok:
            return None, message
        ok, message = self._validate_input(lut_path, "LUT file")
        if not ok:
            return None, message

        ts = timestamp()
        ext = ".jpg" if "JPG" in str(output_format).upper() else ".png"
        output_path = project_path("output", "merge_mode", "images", f"{Path(input_path).stem}_LUT_{ts}{ext}")
        ensure_dir(output_path.parent)

        local_lut_path, lut_filter_path = self._prepare_local_lut(lut_path, ts)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-i",
            input_path,
            "-filter_complex",
            f"[0:v]lut3d=file={lut_filter_path}[out]",
            "-map",
            "[out]",
        ]
        cmd.extend(["-q:v", "2"] if ext == ".jpg" else ["-compression_level", "3"])
        cmd.extend(["-y", str(output_path)])

        try:
            result = run_hidden(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return str(output_path), f"Image saved.\n{output_path.name}"
            error = (result.stderr or "Unknown error")[:1000]
            return None, f"Render failed:\n{error}"
        except FileNotFoundError:
            return None, "FFmpeg not found. Please install FFmpeg or run install.bat."
        except Exception as exc:
            return None, f"Error: {exc}"
        finally:
            try:
                local_lut_path.unlink(missing_ok=True)
            except Exception:
                pass


class MergeModeUI:
    """UI action handlers for Merge Mode."""

    def __init__(self) -> None:
        self.engine = MergeModeEngine()

    def render_action(self, video_file: Any, lut_file: Any, codec: str, use_nvenc: bool) -> tuple[str | None, str]:
        return self.engine.render_video(video_file, lut_file, codec, use_nvenc)

    def render_image_action(self, input_image: Any, lut_file: Any, output_format: str) -> tuple[str | None, str]:
        return self.engine.render_image(input_image, lut_file, output_format)

    def render_image_preview_action(self, input_image: Any, lut_file: Any) -> str | None:
        output_path, _message = self.engine.render_image(input_image, lut_file, "PNG")
        return output_path
