from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Optional, Tuple, Dict

import numpy as np


# ============================================================
#                      Utility / Numeric
# ============================================================

def _f32(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float32)

def _clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, np.float32(0.0), np.float32(1.0)).astype(np.float32, copy=False)

def _safe_log2(x: np.ndarray) -> np.ndarray:
    # avoid -inf; keep float32
    return np.log2(np.maximum(x, np.float32(1e-12), dtype=np.float32)).astype(np.float32)

def _safe_exp2(x: np.ndarray) -> np.ndarray:
    return np.exp2(x).astype(np.float32)


# ============================================================
#                 sRGB <-> Linear (for images)
# ============================================================

def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """sRGB (0..1) -> linear (0..1), float32."""
    x = _f32(srgb)
    a = np.float32(0.055)
    t = np.float32(0.04045)
    low = x / np.float32(12.92)
    high = ((x + a) / (np.float32(1.0) + a)) ** np.float32(2.4)
    return np.where(x <= t, low, high).astype(np.float32)

def linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    """Linear (0..1) -> sRGB (0..1), float32."""
    x = _f32(lin)
    a = np.float32(0.055)
    t = np.float32(0.0031308)
    low = x * np.float32(12.92)
    high = (np.float32(1.0) + a) * (x ** (np.float32(1.0) / np.float32(2.4))) - a
    return np.where(x <= t, low, high).astype(np.float32)


# ============================================================
#                    ARRI LogC4-style Curve
# ============================================================

@dataclass(frozen=True)
class LogC4Params:
    """
    LogC4-style piecewise curve parameters.

    Encoding (linear -> log):
      if x <= cut:
          y = e*x + f
      else:
          y = a*log2(b*x + c) + d

    Decoding (log -> linear):
      if y <= e*cut + f:
          x = (y - f)/e
      else:
          x = (2^((y - d)/a) - c)/b

    For strict ARRI conformance, set parameters from the official ARRI LogC4 PDF.
    """
    a: np.float32
    b: np.float32
    c: np.float32
    d: np.float32
    cut: np.float32
    e: np.float32
    f: np.float32

    @staticmethod
    def from_abcd_cut(a: float, b: float, c: float, d: float, cut: float) -> "LogC4Params":
        """
        Convenience constructor: computes toe line (e,f) by matching continuity and slope
        at the cut point (C1 continuity).
        """
        a = np.float32(a); b = np.float32(b); c = np.float32(c); d = np.float32(d); cut = np.float32(cut)

        # y_cut on the log segment
        y_cut = (a * _safe_log2(b * cut + c) + d).astype(np.float32)

        # derivative of log segment at cut:
        # dy/dx = a * (b / (ln(2) * (b*x + c)))
        ln2 = np.float32(np.log(2.0))
        e = (a * (b / (ln2 * (b * cut + c)))).astype(np.float32)

        # f to ensure continuity
        f = (y_cut - e * cut).astype(np.float32)

        return LogC4Params(a=a, b=b, c=c, d=d, cut=cut, e=e, f=f)


class LogC4Curve:
    """
    LogC4-style encoder/decoder operating on float32 arrays.

    Note: This is a "LogC4 form" implementation; supply official parameters for strict match.
    """

    def __init__(self, params: Optional[LogC4Params] = None):
        self.params = params if params is not None else default_logc4_params()

        # Precompute cut in encoded domain for decode branch
        self._y_cut = (self.params.e * self.params.cut + self.params.f).astype(np.float32)

    def encode(self, linear: np.ndarray) -> np.ndarray:
        """Scene-linear -> LogC4-like (float32)."""
        p = self.params
        x = _f32(linear)

        # Allow negative input but push it into toe safely
        x = np.maximum(x, np.float32(0.0), dtype=np.float32)

        y_toe = (p.e * x + p.f).astype(np.float32)
        y_log = (p.a * _safe_log2(p.b * x + p.c) + p.d).astype(np.float32)
        return np.where(x <= p.cut, y_toe, y_log).astype(np.float32)

    def decode(self, logv: np.ndarray) -> np.ndarray:
        """LogC4-like -> scene-linear (float32)."""
        p = self.params
        y = _f32(logv)

        x_toe = (y - p.f) / p.e
        x_log = (_safe_exp2((y - p.d) / p.a) - p.c) / p.b
        x = np.where(y <= self._y_cut, x_toe, x_log).astype(np.float32)
        return np.maximum(x, np.float32(0.0), dtype=np.float32)


def default_logc4_params() -> LogC4Params:
    """
    Default parameters for creative LUT generation.

    The functional form matches ARRI LogC4 (log2 + toe). These values are a robust
    "LogC-like" starting point. Replace with official LogC4 parameters for exact matching.
    """
    # Base constants close to common LogC-style behavior, but using log2.
    # You can replace these directly with ARRI LogC4 table values:
    # (a, b, c, d, cut) then e,f are derived automatically.
    a = 0.0744   # ~= 0.24719 / log2(10)  (scales log2 similar to older log10 form)
    b = 5.5556
    c = 0.0523
    d = 0.3855
    cut = 0.0106
    return LogC4Params.from_abcd_cut(a=a, b=b, c=c, d=d, cut=cut)


# ============================================================
#            LUT Randomizer PRO (LogC4 working space)
# ============================================================

class LUTRandomizerPro:
    """
    Generates creative LUT cubes using:
    - Linear cube -> LogC4-like domain
    - Apply look operations in log domain
    - Convert back to linear, clamp 0..1
    """

    def __init__(self, size: int = 65, seed: Optional[int] = None, logc4_params: Optional[LogC4Params] = None):
        self.size = int(size)
        self.rng = random.Random(seed)
        self.log = LogC4Curve(logc4_params)
        self.identity = self._create_identity_cube(self.size)

    def _create_identity_cube(self, size: int) -> np.ndarray:
        x = np.linspace(0.0, 1.0, size, dtype=np.float32)
        r, g, b = np.meshgrid(x, x, x, indexing="ij")
        cube = np.stack([r, g, b], axis=-1).astype(np.float32)
        return cube

    # ============================================================
    #                    Math Kernels (float32)
    # ============================================================

    @staticmethod
    def _luma(cube: np.ndarray) -> np.ndarray:
        # Rec.709 luma weights in linear domain; ok for creative grading
        return (np.float32(0.2126) * cube[..., 0] +
                np.float32(0.7152) * cube[..., 1] +
                np.float32(0.0722) * cube[..., 2]).astype(np.float32)

    def _apply_contrast_scurve_log(self, log_cube: np.ndarray, amount: float, pivot: float = 0.39) -> np.ndarray:
        """
        Pivot-preserving contrast using Tanh logic.
        Ensures f(pivot) = pivot.
        """
        x = log_cube.astype(np.float32, copy=False)
        p = np.float32(pivot)
        
        # Map amount to steepness
        # 1.0 -> 1.0 slope (Linear)
        # >1.0 -> S-curve
        slope = np.float32(max(0.1, amount * 2.0)) 
        
        # Deviation
        d = x - p
        
        # Tanh curve
        curve = np.tanh(d * slope)
        
        # Normalization factors
        # For d > 0: asymptote is tanh((1-p)*slope)
        norm_high = np.tanh((np.float32(1.0) - p) * slope)
        scale_high = (np.float32(1.0) - p) / norm_high
        
        # For d < 0: asymptote is tanh(-p*slope) = -tanh(p*slope)
        norm_low = np.tanh(p * slope)
        scale_low = p / norm_low
        
        # Apply scaled curve
        y = np.where(d >= 0, 
                     curve * scale_high, 
                     curve * scale_low)
                     
        # Result = pivot + y
        out = p + y
        return out.astype(np.float32)

    def _apply_exposure_log(self, log_cube: np.ndarray, stops: float) -> np.ndarray:
        """
        Exposure in log domain: additive offset.
        (Because log encoding: linear multiply ~= log add.)
        """
        # A stop in log2 corresponds to +1 before scaling; our log encoding scales by 'a'.
        # We approximate exposure as an offset proportional to stops.
        # Using params.a: y = a*log2(...) + d  -> one stop ~= +a
        off = np.float32(stops) * self.log.params.a
        return (log_cube + off).astype(np.float32)

    def _apply_saturation(self, lin_cube: np.ndarray, sat_mult: float) -> np.ndarray:
        """
        Saturation in linear RGB via luma interpolation.
        """
        x = lin_cube.astype(np.float32, copy=False)
        lum = self._luma(x)
        lum3 = np.stack([lum, lum, lum], axis=-1).astype(np.float32)
        s = np.float32(sat_mult)
        out = lum3 + (x - lum3) * s
        return out.astype(np.float32)

    def _apply_vibrance(self, lin_cube: np.ndarray, vib: float) -> np.ndarray:
        """
        Vibrance: boost saturation more in low-sat regions.
        """
        x = lin_cube.astype(np.float32, copy=False)
        vib = np.float32(vib)

        lum = self._luma(x)
        lum3 = np.stack([lum, lum, lum], axis=-1).astype(np.float32)
        chroma = np.max(x, axis=-1) - np.min(x, axis=-1)
        chroma = chroma.astype(np.float32)

        # low chroma -> stronger boost
        boost = (np.float32(1.0) - np.clip(chroma * np.float32(2.0), np.float32(0.0), np.float32(1.0)))
        sat = np.float32(1.0) + vib * boost
        sat = sat[..., None].astype(np.float32)

        out = lum3 + (x - lum3) * sat
        return out.astype(np.float32)

    def _apply_split_tone_lin(self, lin_cube: np.ndarray,
                              shadow_rgb: Tuple[float, float, float],
                              highlight_rgb: Tuple[float, float, float],
                              strength: float) -> np.ndarray:
        """
        Split tone in linear domain using luma-based masks.
        """
        x = lin_cube.astype(np.float32, copy=False)
        lum = self._luma(x)

        sh_mask = np.clip(np.float32(1.0) - lum * np.float32(1.6), np.float32(0.0), np.float32(1.0)).astype(np.float32)
        hi_mask = np.clip(lum * np.float32(1.6) - np.float32(0.6), np.float32(0.0), np.float32(1.0)).astype(np.float32)

        sh_mask = sh_mask[..., None]
        hi_mask = hi_mask[..., None]

        s_col = _f32(shadow_rgb)
        h_col = _f32(highlight_rgb)
        k = np.float32(strength)

        out = x + (s_col * k * sh_mask) + (h_col * k * hi_mask)
        return out.astype(np.float32)

    def _apply_temperature_lin(self, lin_cube: np.ndarray, temp: float) -> np.ndarray:
        """
        Simple temperature tint in linear space (creative).
        temp in [-1..+1].
        """
        x = lin_cube.astype(np.float32, copy=False)
        t = np.float32(np.clip(temp, -1.0, 1.0))
        if np.isclose(t, 0.0):
            return x

        warm = _f32([1.08, 1.00, 0.93])
        cool = _f32([0.93, 1.00, 1.08])
        filt = warm if t > 0 else cool
        s = np.abs(t).astype(np.float32)

        out = x * (np.float32(1.0) - s) + (x * filt) * s
        return out.astype(np.float32)

    def _apply_lift_gamma_gain_lin(self, lin_cube: np.ndarray, lift: float, gamma: float, gain: float) -> np.ndarray:
        """
        Lift/Gamma/Gain in linear space.
        """
        x = lin_cube.astype(np.float32, copy=False)
        lift = np.float32(lift)
        gamma = np.float32(max(gamma, 1e-4))
        gain = np.float32(gain)

        out = (x + lift) * gain
        out = np.clip(out, np.float32(1e-6), np.float32(32.0)).astype(np.float32)
        out = out ** (np.float32(1.0) / gamma)
        return out.astype(np.float32)

    def _soft_clip(self, lin_cube: np.ndarray, knee: float = 1.0, strength: float = 0.15) -> np.ndarray:
        """
        Gentle highlight rolloff in linear domain.
        """
        x = lin_cube.astype(np.float32, copy=False)
        k = np.float32(knee)
        s = np.float32(np.clip(strength, 0.0, 1.0))

        # compress values above knee with a smooth curve
        above = np.maximum(x - k, np.float32(0.0), dtype=np.float32)
        compressed = k + above / (np.float32(1.0) + above * (np.float32(3.0) * s))
        out = np.where(x > k, compressed, x).astype(np.float32)
        return out

    # ============================================================
    #                    Generator Logic
    # ============================================================

    def generate_unique_lut(self, style: str = "Cinematic") -> np.ndarray:
        """
        Returns LUT cube float32 in sRGB 0..1 domain (ready for display/save by 3D LUT tools).
        Pipeline: Identity(sRGB) -> Linear -> LogC4 -> Looks -> Linear -> sRGB.
        """
        # 1. Start with sRGB Identity (0..1)
        srgb = self.identity.copy()
        
        # 2. Convert sRGB -> Linear (Mid Grey 0.18 is now ~0.18 linear)
        lin = srgb_to_linear(srgb)

        # 3. Convert Linear -> LogC4-like working domain
        # (Mid Grey 0.18 linear maps to ~0.39 in LogC4)
        logc = self.log.encode(lin)

        # Subtle global exposure variance (sensor drift)
        logc = self._apply_exposure_log(logc, stops=self.rng.uniform(-0.10, 0.10))

        # Pivot for contrast: Mid Grey in LogC4 is approx 0.39.
        # We pivot around this to avoid lifting shadows/mids unnecessarily.
        MID_GREY_LOG = 0.39

        # Style logic
        s = style or "Random"

        if "Random" in s:
            # Contrast in log domain (Reduced max from 0.95 to 0.80 to prevent crushing)
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.35, 0.80), pivot=MID_GREY_LOG)

            # Back to linear for chroma ops
            lin = self.log.decode(logc)

            # Split tone
            shadow_colors = [
                (0.00, self.rng.uniform(0.04, 0.10), self.rng.uniform(0.10, 0.22)),  # teal/blue
                (self.rng.uniform(0.10, 0.20), 0.00, self.rng.uniform(0.10, 0.22)),  # purple
                (0.00, self.rng.uniform(0.03, 0.08), self.rng.uniform(0.06, 0.12)),  # deep blue
                (self.rng.uniform(0.06, 0.14), self.rng.uniform(0.05, 0.10), 0.00),  # warm brown
            ]
            highlight_colors = [
                (self.rng.uniform(0.12, 0.22), self.rng.uniform(0.06, 0.12), 0.00),  # orange/gold
                (0.00, self.rng.uniform(0.08, 0.16), self.rng.uniform(0.12, 0.22)),  # cyan
                (self.rng.uniform(0.12, 0.22), self.rng.uniform(0.04, 0.10), self.rng.uniform(0.08, 0.14)),  # rose
                (self.rng.uniform(0.08, 0.16), self.rng.uniform(0.14, 0.20), 0.00),  # lime/yellow
            ]
            lin = self._apply_split_tone_lin(
                lin,
                shadow_rgb=self.rng.choice(shadow_colors),
                highlight_rgb=self.rng.choice(highlight_colors),
                strength=self.rng.uniform(0.10, 0.28),
            )

            # Vibrance + moderate saturation
            lin = self._apply_vibrance(lin, vib=self.rng.uniform(0.08, 0.35))
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(0.90, 1.25))

            # Temperature
            lin = self._apply_temperature_lin(lin, temp=self.rng.uniform(-0.25, 0.25))

            # Filmic lift/gamma/gain (Linear domain)
            # Removed negative lift to prevent crushed blacks.
            lin = self._apply_lift_gamma_gain_lin(
                lin,
                lift=self.rng.uniform(0.00, 0.02), # Always >= 0, max 0.02 for safety
                gamma=self.rng.uniform(0.95, 1.05),
                gain=self.rng.uniform(0.96, 1.04),
            )

        elif "Cinematic" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.55, 1.05), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            teal = (0.0, self.rng.uniform(0.05, 0.12), self.rng.uniform(0.10, 0.20))
            orange = (self.rng.uniform(0.12, 0.22), self.rng.uniform(0.06, 0.12), 0.0)
            lin = self._apply_split_tone_lin(lin, teal, orange, strength=self.rng.uniform(0.12, 0.26))
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(0.85, 1.10))

        elif "TikTok" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.30, 0.65), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(1.35, 1.85))
            lin = self._apply_temperature_lin(lin, temp=self.rng.uniform(-0.20, 0.20))
            lin = self._apply_lift_gamma_gain_lin(lin, lift=0.0, gamma=0.95, gain=self.rng.uniform(1.02, 1.10))

        elif "Vintage" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.20, 0.55), pivot=MID_GREY_LOG+0.05)
            lin = self.log.decode(logc)

            lin = self._apply_lift_gamma_gain_lin(lin, lift=self.rng.uniform(0.01, 0.05), gamma=1.10, gain=0.92)
            lin = lin + _f32([0.03, 0.02, 0.00]) * np.float32(self.rng.uniform(0.4, 0.8))
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(0.55, 0.80))

        elif "Cyberpunk" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.65, 1.10), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            pink = (0.18, 0.0, 0.18)
            cyan = (0.0, 0.18, 0.24)
            lin = self._apply_split_tone_lin(lin, pink, cyan, strength=self.rng.uniform(0.22, 0.36))
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(1.25, 1.55))

        elif "B&W" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.85, 1.35), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)
            lin = self._apply_saturation(lin, sat_mult=0.0)

        elif "Summer Pop" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.45, 0.75), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(1.15, 1.45))
            lin = self._apply_vibrance(lin, vib=self.rng.uniform(0.15, 0.35))
            lin = self._apply_lift_gamma_gain_lin(lin, lift=0.00, gamma=0.95, gain=1.05)
            lin = self._apply_temperature_lin(lin, temp=self.rng.uniform(0.10, 0.28))

        elif "Neon Tokyo" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.70, 1.15), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            purple = (0.10, 0.0, 0.14)
            aqua = (0.0, 0.12, 0.18)
            lin = self._apply_split_tone_lin(lin, purple, aqua, strength=self.rng.uniform(0.18, 0.32))
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(1.15, 1.55))

        elif "Candy Pastel" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.20, 0.45), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            lin = self._apply_lift_gamma_gain_lin(lin, lift=0.02, gamma=0.90, gain=1.08)
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(1.05, 1.25))
            lin = lin + _f32([0.02, 0.00, 0.015])

        elif "Fuji Velvia" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.80, 1.20), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(1.15, 1.40))
            lin = lin + _f32([0.015, -0.008, 0.015])

        elif "Bleach Bypass" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.95, 1.45), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(0.20, 0.45))
            lin = self._apply_temperature_lin(lin, temp=-0.10)

        elif "Matrix Green" in s:
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.60, 1.00), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)

            lin = lin * _f32([0.92, 1.08, 0.92])
            lin = lin + _f32([0.0, 0.015, 0.0])
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(0.65, 0.90))

        else:
            # Fallback
            logc = self._apply_contrast_scurve_log(logc, amount=self.rng.uniform(0.45, 0.85), pivot=MID_GREY_LOG)
            lin = self.log.decode(logc)
            lin = self._apply_saturation(lin, sat_mult=self.rng.uniform(0.90, 1.15))

        # Gentle highlight rolloff (Linear Domain)
        lin = self._soft_clip(lin, knee=1.0, strength=0.18)

        # 4. Convert Linear -> sRGB (for display)
        # We must return sRGB values because the app expects the LUT to map sRGB->sRGB
        srgb_out = linear_to_srgb(lin)

        return _clip01(srgb_out)

    # ============================================================
    #                      LUT I/O (.cube)
    # ============================================================

    def save_cube(self, cube_data: np.ndarray, file_path: str, name: str = "RandomLUT"):
        cube_data = _f32(cube_data)
        n = int(cube_data.shape[0])
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f'TITLE "Gen_{name}"\n')
            f.write(f"LUT_3D_SIZE {n}\n")
            f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
            f.write("DOMAIN_MAX 1.0 1.0 1.0\n\n")
            # .cube ordering: blue fastest? many tools accept this common ordering:
            for b in range(n):
                for g in range(n):
                    for r in range(n):
                        p = cube_data[r, g, b]
                        f.write(f"{float(p[0]):.6f} {float(p[1]):.6f} {float(p[2]):.6f}\n")

    # ============================================================
    #                 LUT Application (Trilinear)
    # ============================================================

    @staticmethod
    def _to_float01(image_array: np.ndarray) -> np.ndarray:
        if image_array.dtype == np.uint8:
            return (image_array.astype(np.float32) / np.float32(255.0)).astype(np.float32)
        if image_array.dtype == np.uint16:
            return (image_array.astype(np.float32) / np.float32(65535.0)).astype(np.float32)
        return image_array.astype(np.float32)

    @staticmethod
    def apply_lut_to_image_fast(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
        """
        Apply LUT with vectorized trilinear interpolation.
        Returns float32 in 0..1.
        """
        img = LUTRandomizerPro._to_float01(image_array)
        lut = _f32(lut_cube)

        h, w, _ = img.shape
        n = int(lut.shape[0])
        scale = np.float32(n - 1)

        flat = img.reshape(-1, 3).astype(np.float32)
        flat = _clip01(flat)

        p = flat * scale  # [0..n-1]
        i0 = np.floor(p).astype(np.int32)
        f = (p - i0.astype(np.float32)).astype(np.float32)
        i1 = np.minimum(i0 + 1, n - 1)

        r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
        r1, g1, b1 = i1[:, 0], i1[:, 1], i1[:, 2]
        fr, fg, fb = f[:, 0:1], f[:, 1:2], f[:, 2:3]  # keep as (N,1)

        c000 = lut[r0, g0, b0]
        c100 = lut[r1, g0, b0]
        c010 = lut[r0, g1, b0]
        c110 = lut[r1, g1, b0]
        c001 = lut[r0, g0, b1]
        c101 = lut[r1, g0, b1]
        c011 = lut[r0, g1, b1]
        c111 = lut[r1, g1, b1]

        c00 = c000 * (1 - fr) + c100 * fr
        c10 = c010 * (1 - fr) + c110 * fr
        c01 = c001 * (1 - fr) + c101 * fr
        c11 = c011 * (1 - fr) + c111 * fr

        c0 = c00 * (1 - fg) + c10 * fg
        c1 = c01 * (1 - fg) + c11 * fg

        out = c0 * (1 - fb) + c1 * fb
        out = out.reshape(h, w, 3).astype(np.float32)

        return _clip01(out)

    @staticmethod
    def apply_lut_to_image_fast_uint8(image_array: np.ndarray, lut_cube: np.ndarray) -> np.ndarray:
        out = LUTRandomizerPro.apply_lut_to_image_fast(image_array, lut_cube)
        return (out * np.float32(255.0) + np.float32(0.5)).astype(np.uint8)


# Backwards-compatible name (drop-in replacement style)
LUTRandomizer = LUTRandomizerPro