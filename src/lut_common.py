"""Shared utilities for LUT Studio Generator.

This module centralizes file-path handling, image conversion, LUT I/O, and LUT
application so the app does not duplicate the same low-level code across image,
video, preset, and merge modes.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image

from lut_accel import (
    NUMBA_AVAILABLE,
    acceleration_status,
    apply_lut_trilinear_fast,
    apply_lut_uint8_fast,
    create_identity_cube_fast,
)

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent if MODULE_DIR.name.lower() == "src" else MODULE_DIR


def project_path(*parts: str) -> Path:
    """Return an absolute path inside the project root."""
    return PROJECT_ROOT.joinpath(*parts)


def ensure_dir(path: str | os.PathLike[str]) -> Path:
    """Create a directory and return it as a Path."""
    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def timestamp() -> int:
    """Return a compact integer timestamp for generated filenames."""
    return int(time.time())


def safe_slug(value: str | None, fallback: str = "LUT") -> str:
    """Make a short filesystem-safe uppercase slug."""
    text = (value or fallback).split(" ")[0].upper().replace("/", "-")
    text = re.sub(r"[^A-Z0-9_-]+", "_", text).strip("_")
    return text or fallback.upper()


def resolve_upload_path(upload: Any) -> str | None:
    """Normalize Gradio uploads, file objects, Path objects, or strings to a path."""
    if upload is None:
        return None
    if isinstance(upload, (str, os.PathLike)):
        return os.fspath(upload)
    for attr in ("name", "path"):
        value = getattr(upload, attr, None)
        if value:
            return os.fspath(value)
    return None


def find_ffmpeg() -> str:
    """Find bundled FFmpeg first, then fall back to PATH."""
    candidates = [
        project_path("bin", "ffmpeg", "ffmpeg.exe"),
        project_path("bin", "ffmpeg", "ffmpeg"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "ffmpeg"


def derive_ffprobe_path(ffmpeg_path: str) -> str:
    """Derive ffprobe from an ffmpeg path or command name."""
    path = Path(ffmpeg_path)
    name = path.name.lower()
    if name == "ffmpeg.exe":
        return str(path.with_name("ffprobe.exe"))
    if name == "ffmpeg" and path.parent != Path("."):
        return str(path.with_name("ffprobe"))
    return "ffprobe"


def hidden_startupinfo() -> subprocess.STARTUPINFO | None:
    """Hide subprocess console windows on Windows."""
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        startupinfo.wShowWindow = subprocess.SW_HIDE
    except AttributeError:
        pass
    return startupinfo


def run_hidden(cmd: Iterable[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with Windows console hiding enabled by default."""
    return subprocess.run(
        list(cmd),
        startupinfo=hidden_startupinfo(),
        **kwargs,
    )


def create_identity_cube(size: int) -> np.ndarray:
    """Create an RGB identity LUT cube as float32.

    Uses a Numba parallel kernel when available; otherwise falls back to NumPy.
    """
    size = int(size)
    accelerated = create_identity_cube_fast(size)
    if accelerated is not None:
        return accelerated
    x = np.linspace(0.0, 1.0, size, dtype=np.float32)
    r, g, b = np.meshgrid(x, x, x, indexing="ij")
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def image_to_rgb_array(image: Any) -> np.ndarray:
    """Convert PIL/numpy image input to an RGB numpy array."""
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGB"))

    arr = np.asarray(image)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    elif arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    elif arr.ndim != 3 or arr.shape[-1] < 3:
        raise ValueError("Expected an image with at least 3 color channels.")
    return arr[..., :3]


def resize_for_preview(image: Any, preview_size_mode: str = "Original (no changes)", preview_max_side: int = 1024) -> Image.Image:
    """Return an RGB PIL image resized for preview according to the selected settings."""
    source = image.convert("RGB") if isinstance(image, Image.Image) else Image.fromarray(image_to_rgb_array(image)).convert("RGB")
    if "Original" in str(preview_size_mode):
        return source
    try:
        max_side = int(float(preview_max_side))
    except (TypeError, ValueError):
        max_side = 1024
    if max_side <= 0:
        max_side = 1024
    resized = source.copy()
    resized.thumbnail((max_side, max_side))
    return resized


def to_float01(image_array: np.ndarray) -> np.ndarray:
    """Convert an RGB array to float32 0..1."""
    arr = image_to_rgb_array(image_array)
    if arr.dtype == np.uint8:
        return arr.astype(np.float32) / np.float32(255.0)
    if arr.dtype == np.uint16:
        return arr.astype(np.float32) / np.float32(65535.0)
    if np.issubdtype(arr.dtype, np.integer):
        return arr.astype(np.float32) / np.float32(np.iinfo(arr.dtype).max)

    arr = arr.astype(np.float32)
    max_value = float(np.nanmax(arr)) if arr.size else 1.0
    if max_value > 1.0:
        arr = arr / (np.float32(255.0) if max_value <= 255.0 else np.float32(65535.0))
    return np.clip(arr, 0.0, 1.0).astype(np.float32)


def clip01(values: np.ndarray) -> np.ndarray:
    """Clamp values to 0..1 as float32."""
    return np.clip(values, np.float32(0.0), np.float32(1.0)).astype(np.float32, copy=False)


def _validate_lut_cube(lut: np.ndarray) -> None:
    if lut.ndim != 4 or lut.shape[-1] != 3 or lut.shape[0] != lut.shape[1] or lut.shape[1] != lut.shape[2]:
        raise ValueError("LUT cube must have shape (N, N, N, 3).")


def apply_lut_trilinear(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
    """Apply a 3D LUT using trilinear interpolation.

    Uses a Numba CPU-parallel kernel when available and falls back to a
    vectorized NumPy implementation otherwise. Returns float32 RGB in 0..1.
    """
    img = to_float01(image_array)
    lut = np.asarray(lut_cube, dtype=np.float32)
    _validate_lut_cube(lut)

    accelerated = apply_lut_trilinear_fast(img, lut)
    if accelerated is not None:
        return accelerated

    height, width, _ = img.shape
    n = int(lut.shape[0])
    scale = np.float32(n - 1)

    flat = clip01(img.reshape(-1, 3))
    pos = flat * scale
    idx0 = np.floor(pos).astype(np.int32)
    frac = (pos - idx0.astype(np.float32)).astype(np.float32)
    idx1 = np.minimum(idx0 + 1, n - 1)

    r0, g0, b0 = idx0[:, 0], idx0[:, 1], idx0[:, 2]
    r1, g1, b1 = idx1[:, 0], idx1[:, 1], idx1[:, 2]
    fr, fg, fb = frac[:, 0:1], frac[:, 1:2], frac[:, 2:3]

    c000 = lut[r0, g0, b0]
    c100 = lut[r1, g0, b0]
    c010 = lut[r0, g1, b0]
    c110 = lut[r1, g1, b0]
    c001 = lut[r0, g0, b1]
    c101 = lut[r1, g0, b1]
    c011 = lut[r0, g1, b1]
    c111 = lut[r1, g1, b1]

    c00 = c000 * (1.0 - fr) + c100 * fr
    c10 = c010 * (1.0 - fr) + c110 * fr
    c01 = c001 * (1.0 - fr) + c101 * fr
    c11 = c011 * (1.0 - fr) + c111 * fr
    c0 = c00 * (1.0 - fg) + c10 * fg
    c1 = c01 * (1.0 - fg) + c11 * fg
    out = c0 * (1.0 - fb) + c1 * fb

    return clip01(out.reshape(height, width, 3))


def apply_lut_uint8(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
    """Apply a LUT and return uint8 RGB for Gradio/PIL display."""
    img = to_float01(image_array)
    lut = np.asarray(lut_cube, dtype=np.float32)
    _validate_lut_cube(lut)

    accelerated = apply_lut_uint8_fast(img, lut)
    if accelerated is not None:
        return accelerated
    return (apply_lut_trilinear(img, lut) * np.float32(255.0) + np.float32(0.5)).astype(np.uint8)


def save_cube(cube_data: np.ndarray, file_path: str | os.PathLike[str], name: str = "LUT") -> str:
    """Write a .cube LUT file and return its path."""
    cube = np.asarray(cube_data, dtype=np.float32)
    if cube.ndim != 4 or cube.shape[-1] != 3:
        raise ValueError("cube_data must have shape (N, N, N, 3).")

    n = int(cube.shape[0])
    path = Path(file_path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f'TITLE "{name}"\n')
        handle.write(f"LUT_3D_SIZE {n}\n")
        handle.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        handle.write("DOMAIN_MAX 1.0 1.0 1.0\n\n")
        for b in range(n):
            for g in range(n):
                for r in range(n):
                    pixel = cube[r, g, b]
                    handle.write(f"{float(pixel[0]):.6f} {float(pixel[1]):.6f} {float(pixel[2]):.6f}\n")
    return str(path)
