"""
Image Mode Engine for LUT Studio Generator
Combines Presets Mode and Manual Mode (Color Grading) functionalities.
"""

import os
import time
import numpy as np
from PIL import Image
DEFAULT_PREVIEW_PATH = os.path.join("assets", "reference_sample.png")

# Lazy / Dynamic imports or alias to allow runtime selection
from randomizer_stochastic_parametric import LUTRandomizer as StandardRandomizer
from randomizer_arri_logc4 import LUTRandomizer as ProRandomizer
from settings import DEFAULT_LOGIC_ENGINE, get_grid_size

def ensure_sample_image():
    """Create a default sample image if none exists."""
    if not os.path.exists(DEFAULT_PREVIEW_PATH):
        # Ensure directory exists
        os.makedirs(os.path.dirname(DEFAULT_PREVIEW_PATH), exist_ok=True)
        
        w, h = 1024, 1024
        x = np.linspace(0, 1, w)
        y = np.linspace(0, 1, h)
        xv, yv = np.meshgrid(x, y)
        img = np.stack([xv, yv, 1-xv], axis=-1)
        img += np.random.normal(0, 0.02, img.shape)
        img = np.clip(img, 0, 1)
        Image.fromarray((img * 255).astype(np.uint8)).save(DEFAULT_PREVIEW_PATH)

def save_image_local(image, prefix="saved_image"):
    """Save PIL Image to output/images folder."""
    if image is None:
        return None
    
    # Handle Numpy Array (Gradio defaulting to numpy)
    if isinstance(image, np.ndarray):
        if image.dtype == np.float32 or image.dtype == np.float64:
            image = (image * 255).astype(np.uint8)
        elif image.dtype != np.uint8:
            image = image.astype(np.uint8)
        
        image = Image.fromarray(image)
    
    # Ensure output directory exists
    save_dir = os.path.join("output", "images")
    os.makedirs(save_dir, exist_ok=True)
    
    # Generate filename
    ts = int(time.time())
    filename = f"{prefix}_{ts}.png"
    filepath = os.path.join(save_dir, filename)
    
    # Save
    image.save(filepath)
    return filepath

# ==========================================
#              PRESETS ENGINE
# ==========================================

class PresetsEngine:
    """Engine for handling preset-based LUT generation."""
    
    def __init__(self):
        self.lut_data = None
        self.randomizer = None
        self.style = None
        self.size = None
    
    
    def generate_preview_full(self, style, quality, user_img, logic_engine=DEFAULT_LOGIC_ENGINE):
        """Generate full quality preview (original resolution) - stores LUT for later building."""
        size = get_grid_size(quality)
        
        # Select Engine
        if "ARRI" in logic_engine:
            self.randomizer = ProRandomizer(size=size)
        else:
            self.randomizer = StandardRandomizer(size=size)
            
        self.lut_data = self.randomizer.generate_unique_lut(style)
        self.style = style
        self.size = size
        
        if user_img is None:
            ensure_sample_image()
            user_img = Image.open(DEFAULT_PREVIEW_PATH)
        
        # No resize - use original resolution
        src_arr = np.array(user_img)
        preview_arr = self.randomizer.apply_lut_to_image_fast_uint8(src_arr, self.lut_data)
        
        return Image.fromarray(preview_arr)
    
    def build_lut(self):
        """Build and save the .cube file from stored LUT data."""
        if self.lut_data is None:
            return None
        
        ts = int(time.time())
        safe_style = self.style.split(' ')[0].upper().replace("/", "-")
        filename = f"LUT_{safe_style}_{self.size}grid_{ts}.cube"
        
        os.makedirs(os.path.join("output", "preset_mode"), exist_ok=True)
        out_path = os.path.join("output", "preset_mode", filename)
        
        self.randomizer.save_cube(self.lut_data, out_path, name=f"{safe_style}_{ts}")
        
        return out_path


# ==========================================
#        MANUAL / COLOR GRADING ENGINE
# ==========================================

class ManualLUTEngine:
    def __init__(self, size=65):
        self.size = size
        self.identity = self._create_identity_cube(size)

    def _create_identity_cube(self, size):
        x = np.linspace(0, 1, size)
        r, g, b = np.meshgrid(x, x, x, indexing='ij')
        cube = np.stack([r, g, b], axis=-1)
        return cube.astype(np.float32)

    # ==========================================
    #       AUTO-ANALYSIS LOGIC (FULL)
    # ==========================================
    
    def analyze_image_full(self, image_array):
        """
        Analyzes image and returns optimal settings for:
        [Exp, Cont, High, Shad, White, Black, Temp, Vib, Sat]
        """
        if image_array is None:
            return 0, 0, 0, 0, 0, 0, 0, 0, 0

        # Convert to float32 0..1 (auto-detect input format)
        if image_array.dtype == np.uint8:
            img = image_array.astype(np.float32) / 255.0
        elif image_array.dtype == np.uint16:
            img = image_array.astype(np.float32) / 65535.0
        else:
            # Already float
            img = image_array.astype(np.float32)
        
        # --- LUMINANCE STATS ---
        lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
        mean_lum = np.mean(lum)
        std_lum = np.std(lum)
        p5 = np.percentile(lum, 5)
        p95 = np.percentile(lum, 95)
        min_lum = np.min(lum)
        max_lum = np.max(lum)

        # 1. Exposure (Target ~0.48)
        exp_diff = 0.48 - mean_lum
        exposure_val = int(exp_diff * 150) 

        # 2. Contrast (Target std ~0.25)
        cont_diff = 0.25 - std_lum
        contrast_val = int(cont_diff * 200)
        contrast_val = np.clip(contrast_val, -20, 40)

        # 3. Highlights (Recover if clipped)
        high_val = -1 * int((p95 - 0.7) * 120) if p95 > 0.85 else 0
        high_val = np.clip(high_val, -80, 0)

        # 4. Shadows (Lift if crushed)
        shad_val = int((0.15 - p5) * 200) if p5 < 0.15 else -10
        shad_val = np.clip(shad_val, -20, 60)

        # 5. Whites
        whites_val = int((1.0 - max_lum) * 100) if max_lum < 0.9 else 0
        
        # 6. Blacks
        blacks_val = -1 * int(min_lum * 150) if min_lum > 0.05 else 0

        # --- COLOR STATS ---
        
        # 7. Temperature (Gray World Assumption)
        # Calculate average R, G, B
        avg_rgb = np.mean(img, axis=(0, 1))
        r_avg, g_avg, b_avg = avg_rgb[0], avg_rgb[1], avg_rgb[2]
        
        # If Blue > Red, image is Cool -> Add Warmth (+Temp)
        # If Red > Blue, image is Warm -> Add Coolness (-Temp)
        # We aim to balance them slightly, but not kill the vibe completely.
        temp_diff = b_avg - r_avg
        # Scale factor
        temp_val = int(temp_diff * 120) 
        temp_val = np.clip(temp_val, -40, 40) # Don't overcorrect
        
        # 8 & 9. Saturation & Vibrance
        # Simple Saturation map: (Max - Min) / Max
        max_c = np.max(img, axis=2)
        min_c = np.min(img, axis=2)
        # Avoid divide by zero
        sat_map = (max_c - min_c) / (max_c + 1e-5)
        mean_sat = np.mean(sat_map)
        
        # Target saturation ~ 0.25 - 0.30
        sat_diff = 0.28 - mean_sat
        
        if sat_diff > 0:
            # Image is dull -> Boost Vibrance (safer) and slightly Sat
            vib_val = int(sat_diff * 200)
            sat_val = int(sat_diff * 100)
        else:
            # Image is oversaturated -> Reduce Saturation
            vib_val = 0
            sat_val = int(sat_diff * 150)
            
        vib_val = np.clip(vib_val, 0, 60)
        sat_val = np.clip(sat_val, -30, 30)

        # Return tuple of 9 values
        return (
            int(np.clip(exposure_val, -100, 100)),
            int(np.clip(contrast_val, -100, 100)),
            int(np.clip(high_val, -100, 100)),
            int(np.clip(shad_val, -100, 100)),
            int(np.clip(whites_val, -100, 100)),
            int(np.clip(blacks_val, -100, 100)),
            int(temp_val),
            int(vib_val),
            int(sat_val)
        )

    # ==========================================
    #       CORE COLOR SCIENCE MATH
    # ==========================================

    def build_lut(self, exposure, contrast, highlights, shadows, whites, blacks, 
                  temp, tint, vibrance, saturation, 
                  fade, cross_process, bleach):
        """
        Takes slider values (-100 to 100) and returns a 3D Cube.
        """
        cube = self.identity.copy()

        # --- 1. LIGHT CATEGORY ---

        # Exposure
        if exposure != 0:
            factor = 2.0 ** (exposure / 100.0)
            cube = cube * factor

        # Contrast (S-Curve)
        if contrast != 0:
            c_factor = 1.0 + (contrast / 100.0)
            cube = (cube - 0.5) * c_factor + 0.5

        # Tonal Compression & Masks
        lum = 0.2126 * cube[..., 0] + 0.7152 * cube[..., 1] + 0.0722 * cube[..., 2]
        lum = np.expand_dims(lum, axis=-1)

        mask_shadows = np.clip(1.0 - (lum * 2.0), 0, 1)
        mask_highlights = np.clip((lum - 0.5) * 2.0, 0, 1)
        mask_blacks = np.clip(1.0 - (lum * 4.0), 0, 1)
        mask_whites = np.clip((lum - 0.75) * 4.0, 0, 1)

        if shadows != 0:
            cube += (shadows / 400.0) * mask_shadows
        if highlights != 0:
            cube += (highlights / 400.0) * mask_highlights
        if blacks != 0:
            cube += (blacks / 400.0) * mask_blacks
        if whites != 0:
            cube += (whites / 400.0) * mask_whites

        # --- 2. ADDITIONAL (PRO FX) CATEGORY ---
        
        if bleach != 0:
            strength = bleach / 100.0
            bw = lum.copy()
            bw = (bw - 0.5) * 1.5 + 0.5 
            bw = np.clip(bw, 0, 1)
            cube = cube * (1.0 - strength) + bw * strength

        if cross_process != 0:
            strength = cross_process / 100.0
            teal_color = np.array([0.0, 0.3, 0.4]) * strength
            orange_color = np.array([0.4, 0.2, 0.0]) * strength
            cp_shad_mask = np.clip(1.0 - (lum * 1.5), 0, 1)
            cp_high_mask = np.clip((lum * 1.5) - 0.5, 0, 1)
            cube += (teal_color * cp_shad_mask)
            cube += (orange_color * cp_high_mask)

        # --- 3. COLOR CATEGORY ---

        if temp != 0:
            strength = temp / 200.0
            warm_vec = np.array([1.0 + strength, 1.0, 1.0 - strength])
            cube = cube * warm_vec

        if tint != 0:
            t_strength = tint / 200.0
            if t_strength > 0: 
                tint_vec = np.array([1.0 + t_strength, 1.0 - t_strength, 1.0 + t_strength])
            else: 
                tint_vec = np.array([1.0 + t_strength, 1.0 - t_strength, 1.0 + t_strength])
            cube = cube * tint_vec

        if saturation != 0:
            sat_mult = 1.0 + (saturation / 100.0)
            sat_mult = max(0.0, sat_mult)
            lum_stack = np.concatenate([lum, lum, lum], axis=-1)
            cube = lum_stack + (cube - lum_stack) * sat_mult

        if vibrance != 0:
            vib_mult = 1.0 + (vibrance / 100.0)
            max_rgb = np.max(cube, axis=-1, keepdims=True)
            min_rgb = np.min(cube, axis=-1, keepdims=True)
            current_sat = (max_rgb - min_rgb) / (max_rgb + 1e-5)
            vib_mask = 1.0 - current_sat
            lum_stack = np.concatenate([lum, lum, lum], axis=-1)
            color_diff = cube - lum_stack
            cube = lum_stack + color_diff * (1.0 + (vib_mult - 1.0) * vib_mask)

        # --- 4. FINAL POLISH ---

        if fade != 0:
            lift_amount = (fade / 100.0) * 0.25 
            cube = lift_amount + cube * (1.0 - lift_amount)

        return np.clip(cube, 0, 1)

    def save_cube(self, cube_data, file_path, name="ManualLUT"):
        N = cube_data.shape[0]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f'TITLE "{name}"\n')
            f.write(f'LUT_3D_SIZE {N}\n')
            f.write('DOMAIN_MIN 0.0 0.0 0.0\n')
            f.write('DOMAIN_MAX 1.0 1.0 1.0\n\n')
            for b in range(N):
                for g in range(N):
                    for r in range(N):
                        p = cube_data[r, g, b]
                        f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")

    def apply_lut_fast(self, image_array, lut_cube):
        """Apply LUT to image. Returns float32 in 0-1 range for maximum precision."""
        # Convert to float32 0..1 (auto-detect input format)
        if image_array.dtype == np.uint8:
            img = image_array.astype(np.float32) / 255.0
        elif image_array.dtype == np.uint16:
            img = image_array.astype(np.float32) / 65535.0
        else:
            # Already float
            img = image_array.astype(np.float32)
        
        h, w, _ = img.shape
        N = lut_cube.shape[0]
        flat_img = img.reshape(-1, 3)
        
        try:
            from scipy.interpolate import RegularGridInterpolator
            x = np.linspace(0, 1, N)
            interp = RegularGridInterpolator((x, x, x), lut_cube, bounds_error=False, fill_value=None)
            res_flat = interp(flat_img)
        except ImportError:
            indices = (flat_img * (N - 1)).astype(int)
            np.clip(indices, 0, N - 1, out=indices)
            res_flat = lut_cube[indices[:, 0], indices[:, 1], indices[:, 2]]
            
        res_img = res_flat.reshape(h, w, 3)
        # Return float32 for full precision
        return np.clip(res_img, 0, 1).astype(np.float32)
    
    def apply_lut_fast_uint8(self, image_array, lut_cube):
        """Apply LUT and return uint8 for display purposes."""
        result = self.apply_lut_fast(image_array, lut_cube)
        return (result * 255).astype(np.uint8)


class ManualModeUI:
    """UI action handlers for Manual Mode tab."""
    
    def __init__(self, size=65):
        self.size = size
    
    def preview_full_action(self, img_input, exp, cont, high, shad, whites, blacks, 
                            temp, tint, vib, sat, fade, cross, bleach, quality):
        """Updates the preview images (Full Quality - Original Resolution)."""
        self.size = get_grid_size(quality)
        engine = ManualLUTEngine(size=self.size)
        
        lut_data = engine.build_lut(exp, cont, high, shad, whites, blacks, 
                                    temp, tint, vib, sat, fade, cross, bleach)
        
        if img_input is None:
            ensure_sample_image()
            img_input = Image.open(DEFAULT_PREVIEW_PATH)
        
        # No resize - use original resolution
        src_arr = np.array(img_input)
        
        preview_arr = engine.apply_lut_fast_uint8(src_arr, lut_data)
        preview_img = Image.fromarray(preview_arr)
        
        return preview_img, preview_img
    
    def auto_full_action(self, img_input, tint, fade, cross, bleach, quality):
        """
        Analyzes image and returns settings for Light + Color.
        Maintains Tint/Fade/Cross/Bleach as they are artistic choices.
        """
        self.size = get_grid_size(quality)
        engine = ManualLUTEngine(size=self.size)
        
        if img_input is None:
            ensure_sample_image()
            img_input = Image.open(DEFAULT_PREVIEW_PATH)
        
        img_input.thumbnail((1024, 1024))
        src_arr = np.array(img_input)
        
        # CALCULATE AUTO SETTINGS (9 values)
        (n_exp, n_cont, n_high, n_shad, n_wh, n_bl, 
         n_temp, n_vib, n_sat) = engine.analyze_image_full(src_arr)
        
        # GENERATE RESULT
        lut_data = engine.build_lut(n_exp, n_cont, n_high, n_shad, n_wh, n_bl, 
                                    n_temp, tint, n_vib, n_sat,
                                    fade, cross, bleach)
        
        preview_arr = engine.apply_lut_fast_uint8(src_arr, lut_data)
        preview_img = Image.fromarray(preview_arr)
        
        # Return sliders (9 updated) + Images
        return n_exp, n_cont, n_high, n_shad, n_wh, n_bl, n_temp, n_vib, n_sat, preview_img, preview_img
    
    def reset_action(self, img_input):
        """Resets ALL sliders to 0 and returns original image."""
        if img_input is None:
            ensure_sample_image()
            img_input = Image.open(DEFAULT_PREVIEW_PATH)
            
        # Return all 13 sliders as 0, plus the original image
        return 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, img_input, img_input
    
    def build_action(self, exp, cont, high, shad, whites, blacks, 
                     temp, tint, vib, sat, fade, cross, bleach, quality):
        """Generates the .cube file ONLY."""
        self.size = get_grid_size(quality)
        engine = ManualLUTEngine(size=self.size)
        lut_data = engine.build_lut(exp, cont, high, shad, whites, blacks, 
                                    temp, tint, vib, sat, fade, cross, bleach)
        ts = int(time.time())
        filename = f"LUT_Manual_Grade_{ts}.cube"
        os.makedirs(os.path.join("output", "manual_mode"), exist_ok=True)
        out_path = os.path.join("output", "manual_mode", filename)
        engine.save_cube(lut_data, out_path, name=f"Manual_{ts}")
        return out_path
