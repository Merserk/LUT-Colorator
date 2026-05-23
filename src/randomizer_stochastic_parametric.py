"""Stochastic/parametric creative LUT generator."""

from __future__ import annotations

import random
from typing import Sequence

import numpy as np

from lut_common import apply_lut_trilinear, apply_lut_uint8, clip01, create_identity_cube, save_cube
from lut_accel import lift_gamma_gain_fast, saturation_fast, split_tone_fast, temperature_fast


class LUTRandomizer:
    """Generate creative LUT cubes in display-referred RGB space."""

    def __init__(self, size: int = 65, seed: int | None = None):
        self.size = int(size)
        self.rng = random.Random(seed)
        self.identity = create_identity_cube(self.size)

    @staticmethod
    def _luma(cube: np.ndarray) -> np.ndarray:
        return (
            np.float32(0.2126) * cube[..., 0]
            + np.float32(0.7152) * cube[..., 1]
            + np.float32(0.0722) * cube[..., 2]
        ).astype(np.float32)

    def _apply_contrast_scurve(self, cube: np.ndarray, amount: float = 1.0, center: float = 0.5) -> np.ndarray:
        center = np.float32(center + self.rng.uniform(-0.1, 0.1))
        slope = np.float32(3.0 + (amount * 7.0))
        curved = np.float32(1.0) / (np.float32(1.0) + np.exp(-slope * (cube - center)))
        denom = curved.max() - curved.min()
        if denom > 0:
            curved = (curved - curved.min()) / denom
        blend = np.float32(amount * 0.8)
        return (cube * (np.float32(1.0) - blend) + curved * blend).astype(np.float32)

    def _apply_saturation(self, cube: np.ndarray, sat_mult: float) -> np.ndarray:
        accelerated = saturation_fast(cube, sat_mult)
        if accelerated is not None:
            return accelerated.astype(np.float32, copy=False)
        lum = self._luma(cube)
        lum_rgb = np.stack([lum, lum, lum], axis=-1)
        return (lum_rgb + (cube - lum_rgb) * np.float32(sat_mult)).astype(np.float32)

    def _apply_split_tone(
        self,
        cube: np.ndarray,
        shadow_rgb: Sequence[float],
        highlight_rgb: Sequence[float],
        strength: float = 0.5,
    ) -> np.ndarray:
        accelerated = split_tone_fast(
            cube,
            shadow_rgb,
            highlight_rgb,
            strength,
            shadow_mul=1.5,
            highlight_mul=1.5,
            highlight_off=0.5,
            clip_output=True,
        )
        if accelerated is not None:
            return accelerated.astype(np.float32, copy=False)
        lum = self._luma(cube)
        shadow_mask = np.clip(1.0 - (lum * 1.5), 0.0, 1.0)[..., None]
        highlight_mask = np.clip((lum * 1.5) - 0.5, 0.0, 1.0)[..., None]
        shadow = np.asarray(shadow_rgb, dtype=np.float32)
        highlight = np.asarray(highlight_rgb, dtype=np.float32)
        tinted = cube + (shadow * strength * shadow_mask) + (highlight * strength * highlight_mask)
        return clip01(tinted)

    @staticmethod
    def _apply_lift_gamma_gain(cube: np.ndarray, lift: float, gamma: float, gain: float) -> np.ndarray:
        accelerated = lift_gamma_gain_fast(
            cube,
            lift,
            gamma,
            gain,
            min_value=0.001,
            max_value=1.0,
            clip_output=True,
        )
        if accelerated is not None:
            return accelerated.astype(np.float32, copy=False)
        out = (cube + np.float32(lift)) * np.float32(gain)
        out = np.clip(out, np.float32(0.001), np.float32(1.0))
        out = np.power(out, np.float32(1.0) / np.float32(max(gamma, 1e-4)))
        return clip01(out)

    @staticmethod
    def _apply_temperature(cube: np.ndarray, temp_val: float) -> np.ndarray:
        if np.isclose(temp_val, 0.0):
            return cube
        accelerated = temperature_fast(cube, temp_val, warm=(1.1, 1.0, 0.9), cool=(0.9, 1.0, 1.1))
        if accelerated is not None:
            return accelerated.astype(np.float32, copy=False)
        warm_filter = np.asarray([1.1, 1.0, 0.9], dtype=np.float32)
        cool_filter = np.asarray([0.9, 1.0, 1.1], dtype=np.float32)
        filter_vec = warm_filter if temp_val > 0 else cool_filter
        strength = np.float32(abs(temp_val))
        return (cube * (1.0 - strength) + (cube * filter_vec) * strength).astype(np.float32)

    def generate_unique_lut(self, style: str = "Cinematic") -> np.ndarray:
        """Generate a unique LUT for the selected style."""
        cube = self.identity.copy()

        # Subtle camera/sensor variance.
        cube = self._apply_lift_gamma_gain(cube, 0.0, self.rng.uniform(0.96, 1.04), 1.0)

        if "Random" in style:
            cube = self._apply_contrast_scurve(cube, amount=self.rng.uniform(0.3, 0.8))
            shadow_colors = [
                np.asarray([0.0, self.rng.uniform(0.1, 0.3), self.rng.uniform(0.2, 0.4)]),
                np.asarray([self.rng.uniform(0.2, 0.4), 0.0, self.rng.uniform(0.2, 0.4)]),
                np.asarray([0.0, self.rng.uniform(0.1, 0.2), self.rng.uniform(0.1, 0.2)]),
                np.asarray([self.rng.uniform(0.1, 0.2), self.rng.uniform(0.1, 0.2), 0.0]),
            ]
            highlight_colors = [
                np.asarray([self.rng.uniform(0.3, 0.5), self.rng.uniform(0.2, 0.3), 0.0]),
                np.asarray([0.0, self.rng.uniform(0.2, 0.4), self.rng.uniform(0.3, 0.5)]),
                np.asarray([self.rng.uniform(0.3, 0.5), self.rng.uniform(0.1, 0.2), self.rng.uniform(0.2, 0.3)]),
                np.asarray([self.rng.uniform(0.2, 0.4), self.rng.uniform(0.3, 0.4), 0.0]),
            ]
            cube = self._apply_split_tone(
                cube,
                self.rng.choice(shadow_colors),
                self.rng.choice(highlight_colors),
                strength=self.rng.uniform(0.15, 0.35),
            )
            cube = self._apply_saturation(cube, self.rng.uniform(0.85, 1.3))
            cube = self._apply_temperature(cube, self.rng.uniform(-0.15, 0.15))
            cube = self._apply_lift_gamma_gain(
                cube,
                lift=self.rng.uniform(0.0, 0.05),
                gamma=self.rng.uniform(0.92, 1.08),
                gain=self.rng.uniform(0.95, 1.05),
            )

        elif "Cinematic" in style:
            cube = self._apply_contrast_scurve(cube, amount=self.rng.uniform(0.5, 0.9))
            teal = np.asarray([0.0, self.rng.uniform(0.1, 0.3), self.rng.uniform(0.3, 0.5)])
            orange = np.asarray([self.rng.uniform(0.4, 0.6), self.rng.uniform(0.2, 0.4), 0.0])
            cube = self._apply_split_tone(cube, teal, orange, strength=self.rng.uniform(0.2, 0.4))
            cube = self._apply_saturation(cube, self.rng.uniform(0.8, 1.1))

        elif "TikTok" in style:
            cube = self._apply_contrast_scurve(cube, amount=self.rng.uniform(0.3, 0.6))
            cube = self._apply_saturation(cube, self.rng.uniform(1.4, 1.8))
            cube = self._apply_temperature(cube, self.rng.uniform(-0.2, 0.2))
            cube = self._apply_lift_gamma_gain(cube, 0.0, 0.95, self.rng.uniform(1.02, 1.1))

        elif "Vintage" in style:
            cube = self._apply_lift_gamma_gain(cube, self.rng.uniform(0.05, 0.15), 1.1, 0.9)
            cube = cube + np.asarray([0.05, 0.03, 0.0], dtype=np.float32) * self.rng.uniform(0.5, 1.5)
            cube = self._apply_saturation(cube, self.rng.uniform(0.5, 0.75))

        elif "Cyberpunk" in style:
            cube = self._apply_split_tone(cube, [0.4, 0.0, 0.4], [0.0, 0.4, 0.5], strength=self.rng.uniform(0.6, 0.8))
            cube = self._apply_saturation(cube, 1.4)
            cube = self._apply_contrast_scurve(cube, amount=0.7)

        elif "B&W" in style:
            cube = self._apply_saturation(cube, 0.0)
            cube = self._apply_contrast_scurve(cube, amount=self.rng.uniform(0.8, 1.4))

        elif "Summer Pop" in style:
            cube = self._apply_contrast_scurve(cube, amount=0.5)
            cube = self._apply_saturation(cube, self.rng.uniform(1.2, 1.5))
            cube = self._apply_lift_gamma_gain(cube, 0.0, 0.95, 1.05)
            cube = self._apply_temperature(cube, self.rng.uniform(0.1, 0.3))

        elif "Neon Tokyo" in style:
            cube = self._apply_split_tone(cube, [0.2, 0.0, 0.3], [0.0, 0.3, 0.4], strength=0.5)
            cube = self._apply_contrast_scurve(cube, amount=0.8)
            cube = self._apply_saturation(cube, self.rng.uniform(1.2, 1.6))

        elif "Candy Pastel" in style:
            cube = self._apply_contrast_scurve(cube, amount=0.3)
            cube = self._apply_lift_gamma_gain(cube, lift=0.05, gamma=0.9, gain=1.1)
            cube = self._apply_saturation(cube, self.rng.uniform(1.1, 1.3))
            cube = cube + np.asarray([0.03, 0.0, 0.02], dtype=np.float32)

        elif "Fuji Velvia" in style:
            cube = self._apply_contrast_scurve(cube, amount=0.9)
            cube = self._apply_saturation(cube, self.rng.uniform(1.2, 1.4))
            cube = cube + np.asarray([0.02, -0.01, 0.02], dtype=np.float32)

        elif "Bleach Bypass" in style:
            cube = self._apply_saturation(cube, self.rng.uniform(0.2, 0.4))
            cube = self._apply_contrast_scurve(cube, amount=1.2)
            cube = self._apply_temperature(cube, -0.1)

        elif "Matrix Green" in style:
            cube = self._apply_contrast_scurve(cube, amount=0.7)
            cube = cube * np.asarray([0.9, 1.1, 0.9], dtype=np.float32)
            cube = cube + np.asarray([0.0, 0.02, 0.0], dtype=np.float32)
            cube = self._apply_saturation(cube, 0.8)

        return clip01(cube)

    @staticmethod
    def save_cube(cube_data: np.ndarray, file_path: str, name: str = "RandomLUT") -> str:
        return save_cube(cube_data, file_path, name=f"Gen_{name}")

    @staticmethod
    def apply_lut_to_image_fast(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
        return apply_lut_trilinear(image_array, lut_cube)

    @staticmethod
    def apply_lut_to_image_fast_uint8(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
        return apply_lut_uint8(image_array, lut_cube)
