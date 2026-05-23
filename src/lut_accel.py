"""Optional NumPy + Numba acceleration kernels for LUT Studio.

The app always keeps the NumPy code path as a fallback.  When Numba is
installed, the functions in this module use `parallel=True` + `prange` so the
heaviest per-pixel/per-LUT-point work can run across CPU cores.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

NUMBA_AVAILABLE = False
NUMBA_THREADS = 1
_NUMBA_ERROR: str | None = None

try:  # pragma: no cover - availability depends on user environment
    if os.environ.get("LUT_STUDIO_DISABLE_NUMBA", "0").lower() not in {"1", "true", "yes", "on"}:
        from numba import njit, prange, get_num_threads, set_num_threads

        requested = os.environ.get("LUT_STUDIO_NUMBA_THREADS")
        cpu_count = os.cpu_count() or 1
        if requested:
            try:
                set_num_threads(max(1, int(requested)))
            except Exception:
                # Fall back to Numba's own default if the requested value is invalid.
                pass
        else:
            try:
                set_num_threads(cpu_count)
            except Exception:
                pass
        NUMBA_THREADS = int(get_num_threads())
        NUMBA_AVAILABLE = True
    else:
        _NUMBA_ERROR = "disabled by LUT_STUDIO_DISABLE_NUMBA"
except Exception as exc:  # pragma: no cover
    NUMBA_AVAILABLE = False
    NUMBA_THREADS = 1
    _NUMBA_ERROR = str(exc)


def acceleration_status() -> str:
    """Human-readable acceleration status for diagnostics."""
    if NUMBA_AVAILABLE:
        return f"Numba CPU parallel enabled ({NUMBA_THREADS} thread{'s' if NUMBA_THREADS != 1 else ''})"
    return f"NumPy fallback active ({_NUMBA_ERROR or 'Numba not installed'})"


if NUMBA_AVAILABLE:  # pragma: no cover - compiled on the user's machine

    @njit(cache=True, fastmath=True, parallel=True)
    def _identity_cube_kernel(size: int) -> np.ndarray:
        out = np.empty((size, size, size, 3), dtype=np.float32)
        denom = np.float32(size - 1)
        total = size * size * size
        ss = size * size
        for idx in prange(total):
            r = idx // ss
            rem = idx - r * ss
            g = rem // size
            b = rem - g * size
            out[r, g, b, 0] = np.float32(r) / denom
            out[r, g, b, 1] = np.float32(g) / denom
            out[r, g, b, 2] = np.float32(b) / denom
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _apply_lut_float_kernel(img: np.ndarray, lut: np.ndarray) -> np.ndarray:
        h, w, _ = img.shape
        n = lut.shape[0]
        scale = np.float32(n - 1)
        out = np.empty((h, w, 3), dtype=np.float32)
        total = h * w

        for idx in prange(total):
            y = idx // w
            x = idx - y * w

            rf = img[y, x, 0]
            gf = img[y, x, 1]
            bf = img[y, x, 2]
            if rf < 0.0:
                rf = 0.0
            elif rf > 1.0:
                rf = 1.0
            if gf < 0.0:
                gf = 0.0
            elif gf > 1.0:
                gf = 1.0
            if bf < 0.0:
                bf = 0.0
            elif bf > 1.0:
                bf = 1.0

            rp = rf * scale
            gp = gf * scale
            bp = bf * scale

            r0 = int(np.floor(rp))
            g0 = int(np.floor(gp))
            b0 = int(np.floor(bp))
            r1 = r0 + 1
            g1 = g0 + 1
            b1 = b0 + 1
            if r1 >= n:
                r1 = n - 1
            if g1 >= n:
                g1 = n - 1
            if b1 >= n:
                b1 = n - 1

            fr = rp - np.float32(r0)
            fg = gp - np.float32(g0)
            fb = bp - np.float32(b0)
            if r0 == r1:
                fr = 0.0
            if g0 == g1:
                fg = 0.0
            if b0 == b1:
                fb = 0.0

            for c in range(3):
                c000 = lut[r0, g0, b0, c]
                c100 = lut[r1, g0, b0, c]
                c010 = lut[r0, g1, b0, c]
                c110 = lut[r1, g1, b0, c]
                c001 = lut[r0, g0, b1, c]
                c101 = lut[r1, g0, b1, c]
                c011 = lut[r0, g1, b1, c]
                c111 = lut[r1, g1, b1, c]

                c00 = c000 * (1.0 - fr) + c100 * fr
                c10 = c010 * (1.0 - fr) + c110 * fr
                c01 = c001 * (1.0 - fr) + c101 * fr
                c11 = c011 * (1.0 - fr) + c111 * fr
                c0 = c00 * (1.0 - fg) + c10 * fg
                c1 = c01 * (1.0 - fg) + c11 * fg
                value = c0 * (1.0 - fb) + c1 * fb
                if value < 0.0:
                    value = 0.0
                elif value > 1.0:
                    value = 1.0
                out[y, x, c] = value
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _apply_lut_uint8_kernel(img: np.ndarray, lut: np.ndarray) -> np.ndarray:
        h, w, _ = img.shape
        n = lut.shape[0]
        scale = np.float32(n - 1)
        out = np.empty((h, w, 3), dtype=np.uint8)
        total = h * w

        for idx in prange(total):
            y = idx // w
            x = idx - y * w

            rf = img[y, x, 0]
            gf = img[y, x, 1]
            bf = img[y, x, 2]
            if rf < 0.0:
                rf = 0.0
            elif rf > 1.0:
                rf = 1.0
            if gf < 0.0:
                gf = 0.0
            elif gf > 1.0:
                gf = 1.0
            if bf < 0.0:
                bf = 0.0
            elif bf > 1.0:
                bf = 1.0

            rp = rf * scale
            gp = gf * scale
            bp = bf * scale
            r0 = int(np.floor(rp))
            g0 = int(np.floor(gp))
            b0 = int(np.floor(bp))
            r1 = r0 + 1
            g1 = g0 + 1
            b1 = b0 + 1
            if r1 >= n:
                r1 = n - 1
            if g1 >= n:
                g1 = n - 1
            if b1 >= n:
                b1 = n - 1
            fr = rp - np.float32(r0)
            fg = gp - np.float32(g0)
            fb = bp - np.float32(b0)
            if r0 == r1:
                fr = 0.0
            if g0 == g1:
                fg = 0.0
            if b0 == b1:
                fb = 0.0

            for c in range(3):
                c000 = lut[r0, g0, b0, c]
                c100 = lut[r1, g0, b0, c]
                c010 = lut[r0, g1, b0, c]
                c110 = lut[r1, g1, b0, c]
                c001 = lut[r0, g0, b1, c]
                c101 = lut[r1, g0, b1, c]
                c011 = lut[r0, g1, b1, c]
                c111 = lut[r1, g1, b1, c]
                c00 = c000 * (1.0 - fr) + c100 * fr
                c10 = c010 * (1.0 - fr) + c110 * fr
                c01 = c001 * (1.0 - fr) + c101 * fr
                c11 = c011 * (1.0 - fr) + c111 * fr
                c0 = c00 * (1.0 - fg) + c10 * fg
                c1 = c01 * (1.0 - fg) + c11 * fg
                value = c0 * (1.0 - fb) + c1 * fb
                if value < 0.0:
                    value = 0.0
                elif value > 1.0:
                    value = 1.0
                out[y, x, c] = np.uint8(value * 255.0 + 0.5)
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _manual_lut_kernel(
        size: int,
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
    ) -> np.ndarray:
        out = np.empty((size, size, size, 3), dtype=np.float32)
        denom = np.float32(size - 1)
        total = size * size * size
        ss = size * size

        exp_factor = np.float32(1.0)
        if exposure != 0.0:
            exp_factor = np.float32(2.0 ** (exposure / 100.0))
        c_factor = np.float32(1.0 + (contrast / 100.0))
        sat_mult = np.float32(max(0.0, 1.0 + (saturation / 100.0)))
        vib_mult = np.float32(1.0 + (vibrance / 100.0))
        fade_lift = np.float32((fade / 100.0) * 0.25)
        temp_strength = np.float32(temp / 200.0)
        tint_strength = np.float32(tint / 200.0)
        bleach_strength = np.float32(bleach / 100.0)
        cross_strength = np.float32(cross_process / 100.0)

        for idx in prange(total):
            r_i = idx // ss
            rem = idx - r_i * ss
            g_i = rem // size
            b_i = rem - g_i * size

            r = np.float32(r_i) / denom
            g = np.float32(g_i) / denom
            b = np.float32(b_i) / denom

            if exposure != 0.0:
                r *= exp_factor
                g *= exp_factor
                b *= exp_factor
            if contrast != 0.0:
                r = (r - 0.5) * c_factor + 0.5
                g = (g - 0.5) * c_factor + 0.5
                b = (b - 0.5) * c_factor + 0.5

            lum = np.float32(0.2126) * r + np.float32(0.7152) * g + np.float32(0.0722) * b

            mask_shadows = 1.0 - lum * 2.0
            if mask_shadows < 0.0:
                mask_shadows = 0.0
            elif mask_shadows > 1.0:
                mask_shadows = 1.0
            mask_highlights = (lum - 0.5) * 2.0
            if mask_highlights < 0.0:
                mask_highlights = 0.0
            elif mask_highlights > 1.0:
                mask_highlights = 1.0
            mask_blacks = 1.0 - lum * 4.0
            if mask_blacks < 0.0:
                mask_blacks = 0.0
            elif mask_blacks > 1.0:
                mask_blacks = 1.0
            mask_whites = (lum - 0.75) * 4.0
            if mask_whites < 0.0:
                mask_whites = 0.0
            elif mask_whites > 1.0:
                mask_whites = 1.0

            if shadows != 0.0:
                add = np.float32(shadows / 400.0) * mask_shadows
                r += add; g += add; b += add
            if highlights != 0.0:
                add = np.float32(highlights / 400.0) * mask_highlights
                r += add; g += add; b += add
            if blacks != 0.0:
                add = np.float32(blacks / 400.0) * mask_blacks
                r += add; g += add; b += add
            if whites != 0.0:
                add = np.float32(whites / 400.0) * mask_whites
                r += add; g += add; b += add

            if bleach != 0.0:
                bw = (lum - 0.5) * 1.5 + 0.5
                if bw < 0.0:
                    bw = 0.0
                elif bw > 1.0:
                    bw = 1.0
                r = r * (1.0 - bleach_strength) + bw * bleach_strength
                g = g * (1.0 - bleach_strength) + bw * bleach_strength
                b = b * (1.0 - bleach_strength) + bw * bleach_strength

            if cross_process != 0.0:
                shadow_mask = 1.0 - lum * 1.5
                if shadow_mask < 0.0:
                    shadow_mask = 0.0
                elif shadow_mask > 1.0:
                    shadow_mask = 1.0
                highlight_mask = lum * 1.5 - 0.5
                if highlight_mask < 0.0:
                    highlight_mask = 0.0
                elif highlight_mask > 1.0:
                    highlight_mask = 1.0
                r += np.float32(0.0) * cross_strength * shadow_mask + np.float32(0.4) * cross_strength * highlight_mask
                g += np.float32(0.3) * cross_strength * shadow_mask + np.float32(0.2) * cross_strength * highlight_mask
                b += np.float32(0.4) * cross_strength * shadow_mask + np.float32(0.0) * cross_strength * highlight_mask

            if temp != 0.0:
                r *= 1.0 + temp_strength
                b *= 1.0 - temp_strength
            if tint != 0.0:
                r *= 1.0 + tint_strength
                g *= 1.0 - tint_strength
                b *= 1.0 + tint_strength

            if saturation != 0.0:
                r = lum + (r - lum) * sat_mult
                g = lum + (g - lum) * sat_mult
                b = lum + (b - lum) * sat_mult

            if vibrance != 0.0:
                max_rgb = r
                if g > max_rgb:
                    max_rgb = g
                if b > max_rgb:
                    max_rgb = b
                min_rgb = r
                if g < min_rgb:
                    min_rgb = g
                if b < min_rgb:
                    min_rgb = b
                current_sat = (max_rgb - min_rgb) / (max_rgb + 1e-5)
                vib_scale = 1.0 + (vib_mult - 1.0) * (1.0 - current_sat)
                r = lum + (r - lum) * vib_scale
                g = lum + (g - lum) * vib_scale
                b = lum + (b - lum) * vib_scale

            if fade != 0.0:
                r = fade_lift + r * (1.0 - fade_lift)
                g = fade_lift + g * (1.0 - fade_lift)
                b = fade_lift + b * (1.0 - fade_lift)

            if r < 0.0:
                r = 0.0
            elif r > 1.0:
                r = 1.0
            if g < 0.0:
                g = 0.0
            elif g > 1.0:
                g = 1.0
            if b < 0.0:
                b = 0.0
            elif b > 1.0:
                b = 1.0
            out[r_i, g_i, b_i, 0] = r
            out[r_i, g_i, b_i, 1] = g
            out[r_i, g_i, b_i, 2] = b
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _saturation_kernel(cube: np.ndarray, sat_mult: float) -> np.ndarray:
        size0, size1, size2, _ = cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(cube)
        s = np.float32(sat_mult)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            r = cube[i, j, k, 0]
            g = cube[i, j, k, 1]
            b = cube[i, j, k, 2]
            lum = np.float32(0.2126) * r + np.float32(0.7152) * g + np.float32(0.0722) * b
            out[i, j, k, 0] = lum + (r - lum) * s
            out[i, j, k, 1] = lum + (g - lum) * s
            out[i, j, k, 2] = lum + (b - lum) * s
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _vibrance_kernel(cube: np.ndarray, vib: float) -> np.ndarray:
        size0, size1, size2, _ = cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(cube)
        v = np.float32(vib)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            r = cube[i, j, k, 0]
            g = cube[i, j, k, 1]
            b = cube[i, j, k, 2]
            lum = np.float32(0.2126) * r + np.float32(0.7152) * g + np.float32(0.0722) * b
            maxc = r
            if g > maxc:
                maxc = g
            if b > maxc:
                maxc = b
            minc = r
            if g < minc:
                minc = g
            if b < minc:
                minc = b
            chroma = maxc - minc
            boost = 1.0 - min(max(chroma * 2.0, 0.0), 1.0)
            sat = 1.0 + v * boost
            out[i, j, k, 0] = lum + (r - lum) * sat
            out[i, j, k, 1] = lum + (g - lum) * sat
            out[i, j, k, 2] = lum + (b - lum) * sat
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _split_tone_kernel(cube: np.ndarray, sr: float, sg: float, sb: float, hr: float, hg: float, hb: float, strength: float, shadow_mul: float, highlight_mul: float, highlight_off: float, clip_output: bool) -> np.ndarray:
        size0, size1, size2, _ = cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(cube)
        st = np.float32(strength)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            r = cube[i, j, k, 0]
            g = cube[i, j, k, 1]
            b = cube[i, j, k, 2]
            lum = np.float32(0.2126) * r + np.float32(0.7152) * g + np.float32(0.0722) * b
            sh = 1.0 - lum * shadow_mul
            if sh < 0.0:
                sh = 0.0
            elif sh > 1.0:
                sh = 1.0
            hi = lum * highlight_mul - highlight_off
            if hi < 0.0:
                hi = 0.0
            elif hi > 1.0:
                hi = 1.0
            rr = r + sr * st * sh + hr * st * hi
            gg = g + sg * st * sh + hg * st * hi
            bb = b + sb * st * sh + hb * st * hi
            if clip_output:
                if rr < 0.0:
                    rr = 0.0
                elif rr > 1.0:
                    rr = 1.0
                if gg < 0.0:
                    gg = 0.0
                elif gg > 1.0:
                    gg = 1.0
                if bb < 0.0:
                    bb = 0.0
                elif bb > 1.0:
                    bb = 1.0
            out[i, j, k, 0] = rr
            out[i, j, k, 1] = gg
            out[i, j, k, 2] = bb
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _lift_gamma_gain_kernel(cube: np.ndarray, lift: float, gamma: float, gain: float, min_value: float, max_value: float, clip_output: bool) -> np.ndarray:
        size0, size1, size2, _ = cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(cube)
        inv_gamma = np.float32(1.0) / np.float32(max(gamma, 1e-4))
        lf = np.float32(lift)
        gn = np.float32(gain)
        mn = np.float32(min_value)
        mx = np.float32(max_value)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for c in range(3):
                v = (cube[i, j, k, c] + lf) * gn
                if v < mn:
                    v = mn
                elif v > mx:
                    v = mx
                v = v ** inv_gamma
                if clip_output:
                    if v < 0.0:
                        v = 0.0
                    elif v > 1.0:
                        v = 1.0
                out[i, j, k, c] = v
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _temperature_kernel(cube: np.ndarray, temp: float, warm_r: float, warm_g: float, warm_b: float, cool_r: float, cool_g: float, cool_b: float) -> np.ndarray:
        size0, size1, size2, _ = cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(cube)
        t = np.float32(temp)
        strength = abs(t)
        fr = warm_r if t > 0.0 else cool_r
        fg = warm_g if t > 0.0 else cool_g
        fb = warm_b if t > 0.0 else cool_b
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            r = cube[i, j, k, 0]
            g = cube[i, j, k, 1]
            b = cube[i, j, k, 2]
            out[i, j, k, 0] = r * (1.0 - strength) + (r * fr) * strength
            out[i, j, k, 1] = g * (1.0 - strength) + (g * fg) * strength
            out[i, j, k, 2] = b * (1.0 - strength) + (b * fb) * strength
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _srgb_to_linear_kernel(srgb: np.ndarray) -> np.ndarray:
        size0, size1, size2, _ = srgb.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(srgb)
        a = np.float32(0.055)
        t = np.float32(0.04045)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for c in range(3):
                x = srgb[i, j, k, c]
                if x <= t:
                    out[i, j, k, c] = x / np.float32(12.92)
                else:
                    out[i, j, k, c] = ((x + a) / (np.float32(1.0) + a)) ** np.float32(2.4)
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _linear_to_srgb_kernel(lin: np.ndarray) -> np.ndarray:
        size0, size1, size2, _ = lin.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(lin)
        a = np.float32(0.055)
        t = np.float32(0.0031308)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for c in range(3):
                x = lin[i, j, k, c]
                if x < 0.0:
                    x = 0.0
                elif x > 1.0:
                    x = 1.0
                if x <= t:
                    out[i, j, k, c] = x * np.float32(12.92)
                else:
                    out[i, j, k, c] = (np.float32(1.0) + a) * (x ** (np.float32(1.0) / np.float32(2.4))) - a
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _logc4_encode_kernel(linear: np.ndarray, a: float, b: float, c: float, s: float, t: float) -> np.ndarray:
        size0, size1, size2, _ = linear.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(linear)
        ln2 = np.float32(np.log(2.0))
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for ch in range(3):
                x = linear[i, j, k, ch]
                if x < t:
                    v = (x - t) / s
                else:
                    v = (np.log(a * x + 64.0) / ln2 - 6.0) / 14.0 * b + c
                out[i, j, k, ch] = v
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _logc4_decode_kernel(logv: np.ndarray, a: float, b: float, c: float, s: float, t: float) -> np.ndarray:
        size0, size1, size2, _ = logv.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(logv)
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for ch in range(3):
                y = logv[i, j, k, ch]
                if y < 0.0:
                    v = y * s + t
                else:
                    v = (2.0 ** (14.0 * (y - c) / b + 6.0) - 64.0) / a
                if v < 0.0:
                    v = 0.0
                out[i, j, k, ch] = v
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _log_contrast_kernel(log_cube: np.ndarray, amount: float, pivot: float) -> np.ndarray:
        size0, size1, size2, _ = log_cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(log_cube)
        p = np.float32(pivot)
        slope = np.float32(max(0.1, amount * 2.0))
        norm_high = np.tanh((np.float32(1.0) - p) * slope)
        norm_low = np.tanh(p * slope)
        scale_high = (np.float32(1.0) - p) / norm_high
        scale_low = p / norm_low
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for ch in range(3):
                d = log_cube[i, j, k, ch] - p
                curve = np.tanh(d * slope)
                if d >= 0.0:
                    y = curve * scale_high
                else:
                    y = curve * scale_low
                out[i, j, k, ch] = p + y
        return out

    @njit(cache=True, fastmath=True, parallel=True)
    def _soft_clip_kernel(cube: np.ndarray, knee: float, strength: float) -> np.ndarray:
        size0, size1, size2, _ = cube.shape
        total = size0 * size1 * size2
        ss = size1 * size2
        out = np.empty_like(cube)
        k0 = np.float32(knee)
        s = np.float32(min(max(strength, 0.0), 1.0))
        for idx in prange(total):
            i = idx // ss
            rem = idx - i * ss
            j = rem // size2
            k = rem - j * size2
            for c in range(3):
                x = cube[i, j, k, c]
                if x > k0:
                    above = x - k0
                    out[i, j, k, c] = k0 + above / (1.0 + above * (3.0 * s))
                else:
                    out[i, j, k, c] = x
        return out


def _as_f32_contiguous(arr: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(arr, dtype=np.float32)


def create_identity_cube_fast(size: int) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _identity_cube_kernel(int(size))


def apply_lut_trilinear_fast(img_float01: np.ndarray, lut_cube: np.ndarray) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _apply_lut_float_kernel(_as_f32_contiguous(img_float01), _as_f32_contiguous(lut_cube))


def apply_lut_uint8_fast(img_float01: np.ndarray, lut_cube: np.ndarray) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _apply_lut_uint8_kernel(_as_f32_contiguous(img_float01), _as_f32_contiguous(lut_cube))


def build_manual_lut_fast(size: int, params: tuple[float, ...]) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or len(params) != 13:
        return None
    return _manual_lut_kernel(int(size), *[float(v) for v in params])


def saturation_fast(cube: np.ndarray, sat_mult: float) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _saturation_kernel(_as_f32_contiguous(cube), float(sat_mult))


def vibrance_fast(cube: np.ndarray, vib: float) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _vibrance_kernel(_as_f32_contiguous(cube), float(vib))


def split_tone_fast(cube: np.ndarray, shadow_rgb: Any, highlight_rgb: Any, strength: float, *, shadow_mul: float = 1.5, highlight_mul: float = 1.5, highlight_off: float = 0.5, clip_output: bool = True) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    s = np.asarray(shadow_rgb, dtype=np.float32).ravel()
    h = np.asarray(highlight_rgb, dtype=np.float32).ravel()
    return _split_tone_kernel(_as_f32_contiguous(cube), float(s[0]), float(s[1]), float(s[2]), float(h[0]), float(h[1]), float(h[2]), float(strength), float(shadow_mul), float(highlight_mul), float(highlight_off), bool(clip_output))


def lift_gamma_gain_fast(cube: np.ndarray, lift: float, gamma: float, gain: float, *, min_value: float = 0.001, max_value: float = 1.0, clip_output: bool = True) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _lift_gamma_gain_kernel(_as_f32_contiguous(cube), float(lift), float(gamma), float(gain), float(min_value), float(max_value), bool(clip_output))


def temperature_fast(cube: np.ndarray, temp: float, *, warm=(1.1, 1.0, 0.9), cool=(0.9, 1.0, 1.1)) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or abs(float(temp)) <= 1e-12:
        return None
    return _temperature_kernel(_as_f32_contiguous(cube), float(temp), float(warm[0]), float(warm[1]), float(warm[2]), float(cool[0]), float(cool[1]), float(cool[2]))


def srgb_to_linear_fast(srgb: np.ndarray) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or np.asarray(srgb).ndim != 4:
        return None
    return _srgb_to_linear_kernel(_as_f32_contiguous(srgb))


def linear_to_srgb_fast(lin: np.ndarray) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or np.asarray(lin).ndim != 4:
        return None
    return _linear_to_srgb_kernel(_as_f32_contiguous(lin))


def logc4_encode_fast(linear: np.ndarray, a: float, b: float, c: float, s: float, t: float) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or np.asarray(linear).ndim != 4:
        return None
    return _logc4_encode_kernel(_as_f32_contiguous(linear), float(a), float(b), float(c), float(s), float(t))


def logc4_decode_fast(logv: np.ndarray, a: float, b: float, c: float, s: float, t: float) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or np.asarray(logv).ndim != 4:
        return None
    return _logc4_decode_kernel(_as_f32_contiguous(logv), float(a), float(b), float(c), float(s), float(t))


def log_contrast_scurve_fast(log_cube: np.ndarray, amount: float, pivot: float) -> np.ndarray | None:
    if not NUMBA_AVAILABLE or np.asarray(log_cube).ndim != 4:
        return None
    return _log_contrast_kernel(_as_f32_contiguous(log_cube), float(amount), float(pivot))


def soft_clip_fast(cube: np.ndarray, knee: float = 1.0, strength: float = 0.15) -> np.ndarray | None:
    if not NUMBA_AVAILABLE:
        return None
    return _soft_clip_kernel(_as_f32_contiguous(cube), float(knee), float(strength))
