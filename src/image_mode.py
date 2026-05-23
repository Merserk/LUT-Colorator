"""Image-mode engines for preset LUT generation and manual color grading."""

from __future__ import annotations

from typing import Any
import random
import struct
import zlib

import numpy as np
from PIL import Image

from lut_accel import build_manual_lut_fast
from lut_common import (
    apply_lut_trilinear,
    apply_lut_uint8,
    clip01,
    create_identity_cube,
    ensure_dir,
    image_to_rgb_array,
    project_path,
    resize_for_preview,
    safe_slug,
    save_cube,
    timestamp,
    to_float01,
)
from randomizer_arri_logc4 import LUTRandomizer as OfficialProRandomizer
from randomizer_arri_logc4 import LogC4Curve as OfficialLogC4Curve
from randomizer_arri_logc4 import linear_to_srgb as official_linear_to_srgb
from randomizer_arri_logc4 import srgb_to_linear as official_srgb_to_linear
from randomizer_arri_logc4_creative import LUTRandomizer as CreativeProRandomizer
from randomizer_arri_logc4_creative import LogC4Curve as CreativeLogC4Curve
from randomizer_arri_logc4_creative import linear_to_srgb as creative_linear_to_srgb
from randomizer_arri_logc4_creative import srgb_to_linear as creative_srgb_to_linear
from randomizer_stochastic_parametric import LUTRandomizer as StandardRandomizer
from settings import DEFAULT_LOGIC_ENGINE, get_grid_size, get_logic_engine, get_preview_resize_settings, get_save_image_output_depth

DEFAULT_PREVIEW_PATH = project_path("assets", "reference_sample.png")


def ensure_sample_image() -> None:
    """Create a default sample image if assets/reference_sample.png is missing."""
    if DEFAULT_PREVIEW_PATH.exists():
        return

    ensure_dir(DEFAULT_PREVIEW_PATH.parent)
    width, height = 1024, 1024
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)
    xv, yv = np.meshgrid(x, y)
    img = np.stack([xv, yv, 1.0 - xv], axis=-1)
    img += np.random.normal(0.0, 0.02, img.shape).astype(np.float32)
    Image.fromarray((clip01(img) * 255.0).astype(np.uint8)).save(DEFAULT_PREVIEW_PATH)


def get_preview_image(user_img: Any | None) -> Image.Image:
    """Return the uploaded image prepared according to the current preview-size settings."""
    preview_size_mode, preview_max_side = get_preview_resize_settings()
    if user_img is None:
        ensure_sample_image()
        return resize_for_preview(Image.open(DEFAULT_PREVIEW_PATH).convert("RGB"), preview_size_mode, preview_max_side)
    if isinstance(user_img, Image.Image):
        return resize_for_preview(user_img.convert("RGB"), preview_size_mode, preview_max_side)
    return resize_for_preview(Image.fromarray(image_to_rgb_array(user_img)), preview_size_mode, preview_max_side)


def _write_png16_rgb(filepath, arr16: np.ndarray) -> None:
    """Write an uncompressed 16-bit RGB PNG using only the standard library."""
    arr = np.asarray(arr16, dtype=np.uint16)
    if arr.ndim != 3 or arr.shape[-1] != 3:
        raise ValueError("Expected RGB uint16 array with shape (height, width, 3).")
    height, width, _ = arr.shape
    arr_be = arr.astype(">u2", copy=False)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + arr_be[row].tobytes() for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 16, 2, 0, 0, 0)
    with open(filepath, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", ihdr))
        handle.write(chunk(b"IDAT", zlib.compress(raw, level=0)))
        handle.write(chunk(b"IEND", b""))


def save_image_local(image: Any, prefix: str = "saved_image") -> str | None:
    """Save a PIL or numpy image using the configured output depth/format."""
    if image is None:
        return None

    output_dir = ensure_dir(project_path("output", "images"))
    slug = safe_slug(prefix, "image")
    depth = get_save_image_output_depth()
    rgb_float = to_float01(image_to_rgb_array(image))

    if depth == "16-bit PNG":
        filepath = output_dir / f"{slug}_{timestamp()}_16bit.png"
        arr16 = np.clip(rgb_float * np.float32(65535.0) + np.float32(0.5), 0, 65535).astype(np.uint16)
        _write_png16_rgb(filepath, arr16)
        return str(filepath)

    if depth == "32-bit TIFF":
        import tifffile

        filepath = output_dir / f"{slug}_{timestamp()}_32bit_float.tiff"
        tifffile.imwrite(filepath, rgb_float.astype(np.float32, copy=False), photometric="rgb", compression=None)
        return str(filepath)

    filepath = output_dir / f"{slug}_{timestamp()}_8bit.png"
    arr8 = np.clip(rgb_float * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    Image.fromarray(arr8, mode="RGB").save(filepath, compress_level=0, optimize=False)
    return str(filepath)


def make_randomizer(logic_engine: str | None = None, size: int = 65, seed: int | None = None):
    """Select the configured LUT randomizer engine."""
    engine_name = str(logic_engine or get_logic_engine())
    if "Official" in engine_name or "Technical" in engine_name:
        return OfficialProRandomizer(size=size, seed=seed)
    if "Creative" in engine_name or "ARRI LogC4 (Pro)" in engine_name or "ARRI" in engine_name:
        return CreativeProRandomizer(size=size, seed=seed)
    return StandardRandomizer(size=size, seed=seed)


class PresetsEngine:
    """Preset-based LUT generation state and actions."""

    def __init__(self) -> None:
        self.lut_data: np.ndarray | None = None
        self.randomizer: Any | None = None
        self.style: str = "Random"
        self.logic_engine: str = DEFAULT_LOGIC_ENGINE
        self.seed: int | None = None
        self.preview_size: int = 65

    def _build_generated_lut(self, quality: str) -> tuple[np.ndarray, Any, int]:
        """Regenerate the currently selected random look at a requested grid size."""
        size = get_grid_size(quality)
        randomizer = make_randomizer(self.logic_engine, size, seed=self.seed)
        lut_data = randomizer.generate_unique_lut(self.style)
        return lut_data, randomizer, size

    def generate_preview_full(
        self,
        style: str,
        quality: str,
        user_img: Any | None,
        logic_engine: str | None = None,
    ) -> Image.Image:
        """Generate and store a preset LUT, then apply it to the full input image."""
        self.style = style
        self.logic_engine = logic_engine or get_logic_engine()
        self.seed = random.SystemRandom().randrange(0, 2**32)
        self.lut_data, self.randomizer, self.preview_size = self._build_generated_lut(quality)

        source = get_preview_image(user_img)
        preview_arr = self.randomizer.apply_lut_to_image_fast_uint8(np.asarray(source), self.lut_data)
        return Image.fromarray(preview_arr)

    # Backwards-compatible alias for older UI wiring.
    generate_preview_fast = generate_preview_full

    def build_lut(self, quality: str, logic_engine: str | None = None) -> str | None:
        """Save the last generated preset look using the export/build LUT quality."""
        if self.seed is None:
            return None

        if logic_engine:
            self.logic_engine = logic_engine
        lut_data, randomizer, output_size = self._build_generated_lut(quality)
        slug = safe_slug(self.style)
        out_path = project_path("output", "preset_mode", f"LUT_{slug}_{output_size}grid_{timestamp()}.cube")
        return randomizer.save_cube(lut_data, str(out_path), name=slug)


class ManualLUTEngine:
    """Manual color-grading LUT builder and image applier."""

    def __init__(self, size: int = 65) -> None:
        self.size = int(size)
        self.identity = create_identity_cube(self.size)

    @staticmethod
    def _luma(rgb: np.ndarray) -> np.ndarray:
        return (
            np.float32(0.2126) * rgb[..., 0]
            + np.float32(0.7152) * rgb[..., 1]
            + np.float32(0.0722) * rgb[..., 2]
        ).astype(np.float32)

    def analyze_image_full(self, image_array: np.ndarray | None) -> tuple[int, int, int, int, int, int, int, int, int]:
        """Analyze an image and return suggested settings.

        Returns: exposure, contrast, highlights, shadows, whites, blacks,
        temperature, vibrance, saturation.
        """
        if image_array is None:
            return (0, 0, 0, 0, 0, 0, 0, 0, 0)

        img = to_float01(image_array)
        lum = self._luma(img)
        mean_lum = float(np.mean(lum))
        std_lum = float(np.std(lum))
        p5 = float(np.percentile(lum, 5))
        p95 = float(np.percentile(lum, 95))
        min_lum = float(np.min(lum))
        max_lum = float(np.max(lum))

        exposure_val = int((0.48 - mean_lum) * 150)
        contrast_val = int(np.clip((0.25 - std_lum) * 200, -20, 40))
        high_val = int(np.clip(-int((p95 - 0.7) * 120), -80, 0)) if p95 > 0.85 else 0
        shad_val = int(np.clip(int((0.15 - p5) * 200), -20, 60)) if p5 < 0.15 else -10
        whites_val = int((1.0 - max_lum) * 100) if max_lum < 0.9 else 0
        blacks_val = -int(min_lum * 150) if min_lum > 0.05 else 0

        r_avg, _g_avg, b_avg = np.mean(img, axis=(0, 1))
        temp_val = int(np.clip((float(b_avg) - float(r_avg)) * 120, -40, 40))

        max_c = np.max(img, axis=2)
        min_c = np.min(img, axis=2)
        mean_sat = float(np.mean((max_c - min_c) / (max_c + 1e-5)))
        sat_diff = 0.28 - mean_sat
        if sat_diff > 0:
            vib_val = int(sat_diff * 200)
            sat_val = int(sat_diff * 100)
        else:
            vib_val = 0
            sat_val = int(sat_diff * 150)

        return (
            int(np.clip(exposure_val, -100, 100)),
            int(np.clip(contrast_val, -100, 100)),
            int(np.clip(high_val, -100, 100)),
            int(np.clip(shad_val, -100, 100)),
            int(np.clip(whites_val, -100, 100)),
            int(np.clip(blacks_val, -100, 100)),
            temp_val,
            int(np.clip(vib_val, 0, 60)),
            int(np.clip(sat_val, -30, 30)),
        )

    def _apply_manual_adjustments(
        self,
        cube: np.ndarray,
        exposure: float,
        contrast: float,
        highlights: float,
        shadows: float,
        whites: float,
        blacks: float,
        temp: float,
        tint: float,
        vibrance: float,
        saturation: float,
        fade: float,
        cross_process: float,
        bleach: float,
        *,
        final_clip: bool = True,
    ) -> np.ndarray:
        """Apply manual grading controls to a working-domain cube."""
        cube = cube.astype(np.float32, copy=True)

        if exposure:
            cube *= np.float32(2.0 ** (exposure / 100.0))
        if contrast:
            c_factor = np.float32(1.0 + (contrast / 100.0))
            cube = (cube - 0.5) * c_factor + 0.5

        lum = self._luma(cube)[..., None]
        mask_shadows = np.clip(1.0 - (lum * 2.0), 0.0, 1.0)
        mask_highlights = np.clip((lum - 0.5) * 2.0, 0.0, 1.0)
        mask_blacks = np.clip(1.0 - (lum * 4.0), 0.0, 1.0)
        mask_whites = np.clip((lum - 0.75) * 4.0, 0.0, 1.0)

        if shadows:
            cube += (shadows / 400.0) * mask_shadows
        if highlights:
            cube += (highlights / 400.0) * mask_highlights
        if blacks:
            cube += (blacks / 400.0) * mask_blacks
        if whites:
            cube += (whites / 400.0) * mask_whites

        if bleach:
            strength = np.float32(bleach / 100.0)
            bw = np.clip((lum - 0.5) * 1.5 + 0.5, 0.0, 1.0)
            cube = cube * (1.0 - strength) + bw * strength

        if cross_process:
            strength = np.float32(cross_process / 100.0)
            teal = np.asarray([0.0, 0.3, 0.4], dtype=np.float32) * strength
            orange = np.asarray([0.4, 0.2, 0.0], dtype=np.float32) * strength
            cube += teal * np.clip(1.0 - (lum * 1.5), 0.0, 1.0)
            cube += orange * np.clip((lum * 1.5) - 0.5, 0.0, 1.0)

        if temp:
            strength = np.float32(temp / 200.0)
            cube *= np.asarray([1.0 + strength, 1.0, 1.0 - strength], dtype=np.float32)

        if tint:
            strength = np.float32(tint / 200.0)
            cube *= np.asarray([1.0 + strength, 1.0 - strength, 1.0 + strength], dtype=np.float32)

        lum_stack = np.concatenate([lum, lum, lum], axis=-1)
        if saturation:
            sat_mult = max(0.0, 1.0 + (saturation / 100.0))
            cube = lum_stack + (cube - lum_stack) * np.float32(sat_mult)

        if vibrance:
            vib_mult = np.float32(1.0 + (vibrance / 100.0))
            max_rgb = np.max(cube, axis=-1, keepdims=True)
            min_rgb = np.min(cube, axis=-1, keepdims=True)
            current_sat = (max_rgb - min_rgb) / (max_rgb + 1e-5)
            cube = lum_stack + (cube - lum_stack) * (1.0 + (vib_mult - 1.0) * (1.0 - current_sat))

        if fade:
            lift_amount = np.float32((fade / 100.0) * 0.25)
            cube = lift_amount + cube * (1.0 - lift_amount)

        return clip01(cube) if final_clip else cube.astype(np.float32, copy=False)

    def build_lut(
        self,
        exposure: float,
        contrast: float,
        highlights: float,
        shadows: float,
        whites: float,
        blacks: float,
        temp: float,
        tint: float,
        vibrance: float,
        saturation: float,
        fade: float,
        cross_process: float,
        bleach: float,
        logic_engine: str | None = None,
    ) -> np.ndarray:
        """Build a color-grading LUT from slider values.

        Numba accelerates the per-point LUT build when available. The NumPy
        implementation below remains the exact fallback.
        """
        params = (
            exposure,
            contrast,
            highlights,
            shadows,
            whites,
            blacks,
            temp,
            tint,
            vibrance,
            saturation,
            fade,
            cross_process,
            bleach,
        )
        engine_name = str(logic_engine or get_logic_engine())
        if "Official" in engine_name or "Technical" in engine_name:
            lin = official_srgb_to_linear(self.identity)
            logc = OfficialLogC4Curve().encode(lin)
            graded_logc = self._apply_manual_adjustments(logc, *params, final_clip=False)
            return clip01(official_linear_to_srgb(clip01(OfficialLogC4Curve().decode(graded_logc))))

        if "Creative" in engine_name or "ARRI LogC4 (Pro)" in engine_name or "ARRI" in engine_name:
            lin = creative_srgb_to_linear(self.identity)
            logc = CreativeLogC4Curve().encode(lin)
            graded_logc = self._apply_manual_adjustments(logc, *params, final_clip=False)
            return clip01(creative_linear_to_srgb(clip01(CreativeLogC4Curve().decode(graded_logc))))

        accelerated = build_manual_lut_fast(self.size, params)
        if accelerated is not None:
            return accelerated
        return self._apply_manual_adjustments(self.identity, *params)

    @staticmethod
    def save_cube(cube_data: np.ndarray, file_path: str, name: str = "ManualLUT") -> str:
        return save_cube(cube_data, file_path, name=name)

    @staticmethod
    def apply_lut_fast(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
        return apply_lut_trilinear(image_array, lut_cube)

    @staticmethod
    def apply_lut_fast_uint8(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
        return apply_lut_uint8(image_array, lut_cube)


class ManualModeUI:
    """UI actions for the Manual/Color Grading image tab."""

    def __init__(self, size: int = 65) -> None:
        self.size = int(size)

    def _engine_for_quality(self, quality: str) -> ManualLUTEngine:
        self.size = get_grid_size(quality)
        return ManualLUTEngine(size=self.size)

    def preview_full_action(
        self,
        img_input: Any,
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
        quality: str,
        logic_engine: str | None = None,
    ) -> tuple[Image.Image, Image.Image]:
        """Build a LUT from sliders and apply it to the input image."""
        engine = self._engine_for_quality(quality)
        lut_data = engine.build_lut(exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach, logic_engine)
        source = get_preview_image(img_input)
        preview = Image.fromarray(engine.apply_lut_fast_uint8(np.asarray(source), lut_data))
        return preview, preview

    # Backwards-compatible alias for older UI wiring.
    preview_action = preview_full_action

    def auto_full_action(
        self,
        img_input: Any,
        tint: float,
        fade: float,
        cross: float,
        bleach: float,
        quality: str,
        logic_engine: str | None = None,
    ) -> tuple[int, int, int, int, int, int, int, int, int, Image.Image, Image.Image]:
        """Analyze the image, update core sliders, and render the preview."""
        engine = self._engine_for_quality(quality)
        source = get_preview_image(img_input)
        analysis_img = source.copy()
        analysis_img.thumbnail((1024, 1024))

        n_exp, n_cont, n_high, n_shad, n_wh, n_bl, n_temp, n_vib, n_sat = engine.analyze_image_full(np.asarray(analysis_img))
        lut_data = engine.build_lut(n_exp, n_cont, n_high, n_shad, n_wh, n_bl, n_temp, tint, n_vib, n_sat, fade, cross, bleach, logic_engine)
        preview = Image.fromarray(engine.apply_lut_fast_uint8(np.asarray(source), lut_data))
        return n_exp, n_cont, n_high, n_shad, n_wh, n_bl, n_temp, n_vib, n_sat, preview, preview

    def reset_action(self, img_input: Any) -> tuple[int, ...]:
        """Reset sliders and restore the original image."""
        source = get_preview_image(img_input)
        return (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, source, source)

    def build_action(
        self,
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
        quality: str,
        logic_engine: str | None = None,
    ) -> str:
        """Generate a manual-grading .cube file."""
        engine = self._engine_for_quality(quality)
        lut_data = engine.build_lut(exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach, logic_engine)
        out_path = project_path("output", "manual_mode", f"LUT_Manual_Grade_{timestamp()}.cube")
        return engine.save_cube(lut_data, str(out_path), name=f"Manual_{timestamp()}")
