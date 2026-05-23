"""Global settings for LUT Studio Generator."""

from __future__ import annotations

import configparser

from lut_common import ensure_dir, project_path

CONFIG_FILE = project_path("config.ini")

QUALITY_OPTIONS = [
    "Standard (33 Grid - Fast)",
    "Ultra (65 Grid - Recommended Quality)",
    "Extreme (129 Grid - Best Quality)",
]

LOGIC_ENGINE_OPTIONS = [
    "Stochastic Parametric (Standard)",
    "ARRI LogC4 Creative (Pro)",
    "ARRI LogC4 Official (Technical)",
]

PREVIEW_SIZE_OPTIONS = [
    "Original (no changes)",
    "Up to max px (longest side)",
]

SAVE_IMAGE_OUTPUT_DEPTH_OPTIONS = [
    "8-bit PNG",
    "16-bit PNG",
    "32-bit TIFF",
]

LEGACY_LOGIC_ENGINE_ALIASES = {
    "ARRI LogC4 (Pro)": "ARRI LogC4 Creative (Pro)",
}

FALLBACK_QUALITY = "Ultra (65 Grid - Recommended Quality)"
FALLBACK_PREVIEW_QUALITY = "Ultra (65 Grid - Recommended Quality)"
FALLBACK_LOGIC_ENGINE = "ARRI LogC4 Creative (Pro)"
FALLBACK_PREVIEW_SIZE_MODE = "Original (no changes)"
FALLBACK_PREVIEW_MAX_SIDE = 1024
FALLBACK_SAVE_IMAGE_OUTPUT_DEPTH = "8-bit PNG"


def normalize_choice(value: str | None, choices: list[str], fallback: str) -> str:
    """Return value when valid, otherwise fallback."""
    if value in choices:
        return value
    if choices is LOGIC_ENGINE_OPTIONS and value in LEGACY_LOGIC_ENGINE_ALIASES:
        return LEGACY_LOGIC_ENGINE_ALIASES[value]
    return fallback


def normalize_positive_int(value: str | int | float | None, fallback: int) -> int:
    """Return a validated positive integer, otherwise fallback."""
    try:
        ivalue = int(float(value))
        return ivalue if ivalue > 0 else int(fallback)
    except (TypeError, ValueError):
        return int(fallback)


def load_config() -> tuple[str, str, str, str, int, str]:
    """Load settings from config.ini, creating it if needed.

    Returns:
        quality: LUT export/build quality.
        preview_quality: LUT preview quality used for all generated previews.
        logic_engine: Creative LUT generator engine.
        preview_size_mode: Preview resizing mode.
        preview_max_side: Preview max longest side in pixels when resize mode is enabled.
        save_image_output_depth: Output format/depth used by Save Image actions.
    """
    config = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        config.read(CONFIG_FILE)
        if "Settings" in config:
            section = config["Settings"]
            quality = normalize_choice(section.get("quality"), QUALITY_OPTIONS, FALLBACK_QUALITY)
            preview_quality = normalize_choice(section.get("preview_quality"), QUALITY_OPTIONS, FALLBACK_PREVIEW_QUALITY)
            logic = normalize_choice(section.get("logic_engine"), LOGIC_ENGINE_OPTIONS, FALLBACK_LOGIC_ENGINE)
            preview_size_mode = normalize_choice(section.get("preview_size_mode"), PREVIEW_SIZE_OPTIONS, FALLBACK_PREVIEW_SIZE_MODE)
            preview_max_side = normalize_positive_int(section.get("preview_max_side"), FALLBACK_PREVIEW_MAX_SIDE)
            save_depth = normalize_choice(section.get("save_image_output_depth"), SAVE_IMAGE_OUTPUT_DEPTH_OPTIONS, FALLBACK_SAVE_IMAGE_OUTPUT_DEPTH)
            return quality, preview_quality, logic, preview_size_mode, preview_max_side, save_depth

    save_config(FALLBACK_QUALITY, FALLBACK_PREVIEW_QUALITY, FALLBACK_LOGIC_ENGINE, FALLBACK_PREVIEW_SIZE_MODE, FALLBACK_PREVIEW_MAX_SIDE, FALLBACK_SAVE_IMAGE_OUTPUT_DEPTH)
    return FALLBACK_QUALITY, FALLBACK_PREVIEW_QUALITY, FALLBACK_LOGIC_ENGINE, FALLBACK_PREVIEW_SIZE_MODE, FALLBACK_PREVIEW_MAX_SIDE, FALLBACK_SAVE_IMAGE_OUTPUT_DEPTH


def save_config(quality: str, preview_quality: str, logic_engine: str, preview_size_mode: str, preview_max_side: int | float | str, save_image_output_depth: str) -> None:
    """Save settings to config.ini."""
    config = configparser.ConfigParser()
    config["Settings"] = {
        "quality": normalize_choice(quality, QUALITY_OPTIONS, FALLBACK_QUALITY),
        "preview_quality": normalize_choice(preview_quality, QUALITY_OPTIONS, FALLBACK_PREVIEW_QUALITY),
        "logic_engine": normalize_choice(logic_engine, LOGIC_ENGINE_OPTIONS, FALLBACK_LOGIC_ENGINE),
        "preview_size_mode": normalize_choice(preview_size_mode, PREVIEW_SIZE_OPTIONS, FALLBACK_PREVIEW_SIZE_MODE),
        "preview_max_side": str(normalize_positive_int(preview_max_side, FALLBACK_PREVIEW_MAX_SIDE)),
        "save_image_output_depth": normalize_choice(save_image_output_depth, SAVE_IMAGE_OUTPUT_DEPTH_OPTIONS, FALLBACK_SAVE_IMAGE_OUTPUT_DEPTH),
    }
    ensure_dir(CONFIG_FILE.parent)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        config.write(handle)


def get_grid_size(quality_name: str) -> int:
    """Return LUT grid size for a quality display name."""
    if "Extreme" in str(quality_name):
        return 129
    if "Ultra" in str(quality_name):
        return 65
    return 33


DEFAULT_QUALITY, DEFAULT_PREVIEW_QUALITY, DEFAULT_LOGIC_ENGINE, DEFAULT_PREVIEW_SIZE_MODE, DEFAULT_PREVIEW_MAX_SIDE, DEFAULT_SAVE_IMAGE_OUTPUT_DEPTH = load_config()


def get_preview_resize_settings() -> tuple[str, int]:
    """Return the current preview resize mode and max side."""
    _, _, _, preview_size_mode, preview_max_side, _ = load_config()
    return preview_size_mode, preview_max_side


def get_save_image_output_depth() -> str:
    """Return the current Save Image output depth/format setting."""
    *_, save_depth = load_config()
    return save_depth


def get_logic_engine() -> str:
    """Return the current configured LUT logic engine."""
    _, _, logic_engine, _, _, _ = load_config()
    return logic_engine
