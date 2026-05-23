"""Video-mode helpers and UI actions for previewing LUTs on video frames."""

from __future__ import annotations

import random
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from image_mode import ManualLUTEngine, make_randomizer
from lut_common import derive_ffprobe_path, find_ffmpeg, project_path, resolve_upload_path, resize_for_preview, run_hidden, safe_slug, timestamp
from settings import DEFAULT_LOGIC_ENGINE, get_grid_size, get_logic_engine, get_preview_resize_settings

AUTO_FRAME_POSITIONS = (0.20, 0.40, 0.60, 0.80)


def current_preview_max_side() -> int | None:
    """Return the configured preview max size, or None for original size."""
    preview_size_mode, preview_max_side = get_preview_resize_settings()
    if "Original" in str(preview_size_mode):
        return None
    try:
        side = int(float(preview_max_side))
    except (TypeError, ValueError):
        side = 1024
    return max(1, side)


def resize_frame_for_preview(frame: Image.Image | None) -> Image.Image | None:
    """Resize a frame for preview according to the current preview-size settings."""
    if frame is None:
        return None
    preview_size_mode, preview_max_side = get_preview_resize_settings()
    return resize_for_preview(frame, preview_size_mode, preview_max_side)


class VideoLUTEngine:
    """Extract frames from videos and apply LUTs to those frames."""

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = str(Path(ffmpeg_path).resolve()) if ffmpeg_path else find_ffmpeg()

    @property
    def ffprobe_path(self) -> str:
        return derive_ffprobe_path(self.ffmpeg_path)

    def get_video_duration(self, video_file: Any) -> float | None:
        """Return video duration in seconds using ffprobe."""
        video_path = resolve_upload_path(video_file)
        if not video_path:
            return None

        cmd_base = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
        ]

        def run_probe(path: str):
            try:
                return run_hidden(cmd_base + [path], capture_output=True, text=True, timeout=10)
            except Exception as exc:  # ffprobe missing, timeout, permissions, etc.
                return exc

        for attempt in range(3):
            result = run_probe(video_path)
            if hasattr(result, "returncode") and result.returncode == 0:
                try:
                    return float(result.stdout.strip())
                except (TypeError, ValueError):
                    pass

            stderr = getattr(result, "stderr", "") or ""
            if "permission denied" in stderr.lower() or "access is denied" in stderr.lower():
                time.sleep(1.0 if attempt < 2 else 0.0)
            elif attempt < 2:
                time.sleep(0.5)

        # Fallback for temporary-file lock issues.
        temp_copy = f"{video_path}.{timestamp()}.temp"
        try:
            shutil.copy2(video_path, temp_copy)
            result = run_probe(temp_copy)
            if hasattr(result, "returncode") and result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            return None
        finally:
            try:
                Path(temp_copy).unlink(missing_ok=True)
            except Exception:
                pass

        return None

    def extract_frame_at_time(self, video_file: Any, time_seconds: float, output_path: str | None = None) -> Image.Image | None:
        """Extract a single RGB frame at a specific time."""
        video_path = resolve_upload_path(video_file)
        if not video_path:
            return None

        temp_created = output_path is None
        if output_path is None:
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            output_path = handle.name
            handle.close()

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss",
            str(max(0.0, float(time_seconds or 0.0))),
            "-i",
            video_path,
            "-vframes",
            "1",
            "-q:v",
            "2",
            output_path,
        ]

        try:
            result = run_hidden(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and Path(output_path).exists():
                with Image.open(output_path) as frame:
                    return frame.convert("RGB").copy()
        except Exception:
            return None
        finally:
            if temp_created:
                try:
                    Path(output_path).unlink(missing_ok=True)
                except Exception:
                    pass

        return None

    def extract_frames_auto(self, video_file: Any) -> tuple[Image.Image | None, Image.Image | None, Image.Image | None, Image.Image | None]:
        """Extract frames at 20%, 40%, 60%, and 80% of video duration."""
        duration = self.get_video_duration(video_file)
        if not duration or duration <= 0:
            return (None, None, None, None)
        return tuple(self.extract_frame_at_time(video_file, duration * pos) for pos in AUTO_FRAME_POSITIONS)  # type: ignore[return-value]

    @staticmethod
    def apply_lut_to_frame(frame: Image.Image | None, lut_data: np.ndarray, engine: Any, *, max_size: int | None = -1) -> Image.Image | None:
        """Apply a LUT to a frame and return a PIL image."""
        if frame is None:
            return None

        source = frame.convert("RGB") if isinstance(frame, Image.Image) else Image.fromarray(np.asarray(frame)).convert("RGB")
        if max_size == -1:
            max_size = current_preview_max_side()
        if max_size:
            source = source.copy()
            source.thumbnail((max_size, max_size))

        input_array = np.asarray(source)
        if hasattr(engine, "apply_lut_to_image_fast_uint8"):
            colorized = engine.apply_lut_to_image_fast_uint8(input_array, lut_data)
        elif hasattr(engine, "apply_lut_fast_uint8"):
            colorized = engine.apply_lut_fast_uint8(input_array, lut_data)
        else:
            colorized = engine.apply_lut_fast(input_array, lut_data)
            if getattr(colorized, "dtype", None) == np.float32:
                colorized = (colorized * 255).astype(np.uint8)
        return Image.fromarray(colorized)

    def apply_lut_to_frame_full(self, frame: Image.Image | None, lut_data: np.ndarray, engine: Any) -> Image.Image | None:
        """Apply a LUT without resizing the extracted frame."""
        return self.apply_lut_to_frame(frame, lut_data, engine, max_size=None)


class VideoModeUI:
    """UI action handlers for the Video Mode tab."""

    def __init__(self) -> None:
        self.lut_data: np.ndarray | None = None
        self.engine: Any | None = None
        self.style: str = ""
        self.preview_size: int = 65
        self.kind: str | None = None
        self.logic_engine: str = DEFAULT_LOGIC_ENGINE
        self.seed: int | None = None
        self.manual_params: tuple[float, ...] | None = None

    def _store_lut(
        self,
        lut_data: np.ndarray,
        engine: Any,
        style: str,
        size: int,
        *,
        kind: str,
        logic_engine: str | None = None,
        seed: int | None = None,
        manual_params: tuple[float, ...] | None = None,
    ) -> None:
        self.lut_data = lut_data
        self.engine = engine
        self.style = style
        self.preview_size = size
        self.kind = kind
        self.logic_engine = logic_engine or get_logic_engine()
        self.seed = seed
        self.manual_params = manual_params

    @staticmethod
    def _manual_params(
        exp: float,
        cont: float,
        high: float,
        shad: float,
        whites: float,
        blacks: float,
        temp: float,
        tint: float,
        vib: float,
        sat: float,
        fade: float,
        cross: float,
        bleach: float,
    ) -> tuple[float, ...]:
        return (exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach)

    def _build_preset_lut(self, quality: str, style: str, logic_engine: str, seed: int) -> tuple[np.ndarray, Any, int]:
        size = get_grid_size(quality)
        randomizer = make_randomizer(logic_engine, size, seed=seed)
        lut_data = randomizer.generate_unique_lut(style)
        return lut_data, randomizer, size

    def _build_manual_lut(self, quality: str, params: tuple[float, ...], logic_engine: str | None = None) -> tuple[np.ndarray, ManualLUTEngine, int]:
        size = get_grid_size(quality)
        engine = ManualLUTEngine(size=size)
        lut_data = engine.build_lut(*params, logic_engine)
        return lut_data, engine, size

    def store_manual_lut(
        self,
        lut_data: np.ndarray,
        engine: ManualLUTEngine,
        style: str,
        size: int,
        params: tuple[float, ...],
        logic_engine: str | None = None,
    ) -> None:
        """Store an externally built manual LUT, used by app-level auto-adjust."""
        self._store_lut(lut_data, engine, style, size, kind="manual", logic_engine=logic_engine, manual_params=params)

    def auto_preview(
        self,
        video_file: Any,
        style: str,
        quality: str,
        logic_engine: str | None = None,
    ) -> tuple[Any, ...]:
        """Extract four frames and apply a generated preset LUT at preview quality."""
        if video_file is None:
            return (None,) * 8

        video_engine = VideoLUTEngine()
        seed = random.SystemRandom().randrange(0, 2**32)
        active_logic_engine = logic_engine or get_logic_engine()
        lut_data, randomizer, size = self._build_preset_lut(quality, style, active_logic_engine, seed)
        self._store_lut(lut_data, randomizer, style, size, kind="preset", logic_engine=active_logic_engine, seed=seed)

        frames = video_engine.extract_frames_auto(video_file)
        if any(frame is None for frame in frames):
            return (None,) * 8

        display_frames = tuple(resize_frame_for_preview(frame) for frame in frames)
        colorized = [video_engine.apply_lut_to_frame(frame, lut_data, randomizer, max_size=current_preview_max_side()) for frame in frames]
        return tuple(item for pair in zip(display_frames, colorized) for item in pair)

    def grading_preview(
        self,
        video_file: Any,
        quality: str,
        exp: float,
        cont: float,
        high: float,
        shad: float,
        whites: float,
        blacks: float,
        temp: float,
        tint: float,
        vib: float,
        sat: float,
        fade: float,
        cross: float,
        bleach: float,
        logic_engine: str | None = None,
    ) -> tuple[Any, ...]:
        """Extract four frames and apply a manual color-grading LUT at preview quality."""
        if video_file is None:
            return (None,) * 8

        video_engine = VideoLUTEngine()
        params = self._manual_params(exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach)
        active_logic_engine = logic_engine or get_logic_engine()
        lut_data, engine, size = self._build_manual_lut(quality, params, active_logic_engine)
        self._store_lut(lut_data, engine, "ColorGrade", size, kind="manual", logic_engine=active_logic_engine, manual_params=params)

        frames = video_engine.extract_frames_auto(video_file)
        if any(frame is None for frame in frames):
            return (None,) * 8

        display_frames = tuple(resize_frame_for_preview(frame) for frame in frames)
        colorized = [video_engine.apply_lut_to_frame(frame, lut_data, engine, max_size=current_preview_max_side()) for frame in frames]
        return tuple(item for pair in zip(display_frames, colorized) for item in pair)

    def build_lut(self, quality: str, logic_engine: str | None = None) -> str | None:
        """Save the most recently generated video LUT using export/build quality."""
        if logic_engine:
            self.logic_engine = logic_engine
        if self.kind == "preset" and self.seed is not None:
            lut_data, engine, output_size = self._build_preset_lut(quality, self.style or "Video", self.logic_engine, self.seed)
        elif self.kind == "manual" and self.manual_params is not None:
            lut_data, engine, output_size = self._build_manual_lut(quality, self.manual_params, self.logic_engine)
        elif self.lut_data is not None and self.engine is not None:
            # Fallback for legacy state: save exactly what is currently stored.
            lut_data, engine, output_size = self.lut_data, self.engine, int(self.lut_data.shape[0])
        else:
            return None

        ts = timestamp()
        slug = safe_slug(self.style or "Video")
        out_path = project_path("output", "video_mode", f"LUT_VIDEO_{slug}_{output_size}grid_{ts}.cube")
        return engine.save_cube(lut_data, str(out_path), name=f"VIDEO_{slug}_{ts}")

    def get_duration(self, video_file: Any) -> float:
        """Get video duration in seconds, returning 0 when unavailable."""
        return VideoLUTEngine().get_video_duration(video_file) or 0.0

    def extract_manual_frame(self, video_file: Any, time_sec: float) -> Image.Image | None:
        """Extract the manually selected video frame."""
        return resize_frame_for_preview(VideoLUTEngine().extract_frame_at_time(video_file, time_sec))

    def generate_auto_lut_manual(
        self,
        frame: Image.Image | None,
        style: str,
        quality: str,
        logic_engine: str | None = None,
    ) -> Image.Image | None:
        """Generate a new preset LUT at preview quality and apply it to one selected frame."""
        if frame is None:
            return None

        seed = random.SystemRandom().randrange(0, 2**32)
        active_logic_engine = logic_engine or get_logic_engine()
        lut_data, randomizer, size = self._build_preset_lut(quality, style, active_logic_engine, seed)
        self._store_lut(lut_data, randomizer, style, size, kind="preset", logic_engine=active_logic_engine, seed=seed)
        return self.apply_stored_lut_manual(frame)

    def apply_stored_lut_manual(self, frame: Image.Image | None) -> Image.Image | None:
        """Apply the current stored preview LUT to one frame; return original if no LUT exists."""
        if frame is None:
            return None
        if self.lut_data is None or self.engine is None:
            return frame
        return VideoLUTEngine.apply_lut_to_frame(frame, self.lut_data, self.engine, max_size=current_preview_max_side())

    def manual_preview_grading(
        self,
        frame: Image.Image | None,
        quality: str,
        exp: float,
        cont: float,
        high: float,
        shad: float,
        whites: float,
        blacks: float,
        temp: float,
        tint: float,
        vib: float,
        sat: float,
        fade: float,
        cross: float,
        bleach: float,
        logic_engine: str | None = None,
    ) -> Image.Image | None:
        """Build a manual preview LUT from sliders and apply it to one selected frame."""
        if frame is None:
            return None

        params = self._manual_params(exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach)
        active_logic_engine = logic_engine or get_logic_engine()
        lut_data, engine, size = self._build_manual_lut(quality, params, active_logic_engine)
        self._store_lut(lut_data, engine, "ColorGrade", size, kind="manual", logic_engine=active_logic_engine, manual_params=params)
        return self.apply_stored_lut_manual(frame)
