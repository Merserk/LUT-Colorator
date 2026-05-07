import numpy as np
import random

class LUTRandomizer:
    def __init__(self, size=65):
        self.size = size
        self.identity = self._create_identity_cube(size)

    def _create_identity_cube(self, size):
        x = np.linspace(0, 1, size)
        r, g, b = np.meshgrid(x, x, x, indexing='ij')
        cube = np.stack([r, g, b], axis=-1)
        return cube.astype(np.float32)

    # ==========================================
    #              Math Kernels
    # ==========================================

    def _apply_contrast_scurve(self, cube, amount=1.0, center=0.5):
        center = center + random.uniform(-0.1, 0.1)
        slope = 3.0 + (amount * 7.0)
        curved = 1.0 / (1.0 + np.exp(-slope * (cube - center)))
        curved = (curved - curved.min()) / (curved.max() - curved.min())
        return cube * (1.0 - amount*0.8) + curved * (amount*0.8)

    def _apply_saturation(self, cube, sat_mult):
        lum = 0.2126 * cube[..., 0] + 0.7152 * cube[..., 1] + 0.0722 * cube[..., 2]
        lum = np.stack([lum, lum, lum], axis=-1)
        return lum + (cube - lum) * sat_mult

    def _apply_split_tone(self, cube, shadow_rgb, highlight_rgb, strength=0.5):
        lum = 0.2126 * cube[..., 0] + 0.7152 * cube[..., 1] + 0.0722 * cube[..., 2]
        shadow_mask = np.clip(1.0 - (lum * 1.5), 0, 1)[..., None]
        highlight_mask = np.clip((lum * 1.5) - 0.5, 0, 1)[..., None]
        
        s_color = np.array(shadow_rgb, dtype=np.float32)
        h_color = np.array(highlight_rgb, dtype=np.float32)
        
        tinted = cube + (s_color * strength * shadow_mask) + (h_color * strength * highlight_mask)
        return np.clip(tinted, 0, 1)

    def _apply_lift_gamma_gain(self, cube, lift, gamma, gain):
        cube = cube + lift
        cube = cube * gain
        cube = np.clip(cube, 0.001, 1.0)
        cube = np.power(cube, 1.0 / gamma)
        return np.clip(cube, 0, 1)

    def _apply_temperature(self, cube, temp_val):
        if temp_val == 0: return cube
        warm_filter = np.array([1.1, 1.0, 0.9]) 
        cool_filter = np.array([0.9, 1.0, 1.1])
        filter_vec = warm_filter if temp_val > 0 else cool_filter
        strength = abs(temp_val)
        res = cube * filter_vec
        return cube * (1 - strength) + res * strength

    # ==========================================
    #         GENERATOR LOGIC
    # ==========================================

    def generate_unique_lut(self, style="Cinematic"):
        cube = self.identity.copy()
        
        # Global Sensor Drift (Camera Variance)
        global_gamma = random.uniform(0.96, 1.04)
        cube = self._apply_lift_gamma_gain(cube, 0, global_gamma, 1.0)

        # --- RANDOM STYLE (Beautiful & Unique) ---
        if "Random" in style:
            # Random contrast
            cube = self._apply_contrast_scurve(cube, amount=random.uniform(0.3, 0.8))
            
            # Random split tone with beautiful color combinations
            shadow_colors = [
                np.array([0.0, random.uniform(0.1, 0.3), random.uniform(0.2, 0.4)]),  # Teal
                np.array([random.uniform(0.2, 0.4), 0.0, random.uniform(0.2, 0.4)]),  # Purple
                np.array([0.0, random.uniform(0.1, 0.2), random.uniform(0.1, 0.2)]),  # Deep Blue
                np.array([random.uniform(0.1, 0.2), random.uniform(0.1, 0.2), 0.0]),  # Warm Brown
            ]
            highlight_colors = [
                np.array([random.uniform(0.3, 0.5), random.uniform(0.2, 0.3), 0.0]),  # Orange/Gold
                np.array([0.0, random.uniform(0.2, 0.4), random.uniform(0.3, 0.5)]),  # Cyan
                np.array([random.uniform(0.3, 0.5), random.uniform(0.1, 0.2), random.uniform(0.2, 0.3)]),  # Rose
                np.array([random.uniform(0.2, 0.4), random.uniform(0.3, 0.4), 0.0]),  # Lime/Yellow
            ]
            shadow_rgb = random.choice(shadow_colors)
            highlight_rgb = random.choice(highlight_colors)
            cube = self._apply_split_tone(cube, shadow_rgb, highlight_rgb, strength=random.uniform(0.15, 0.35))
            
            # Random saturation (slight boost to desaturated)
            cube = self._apply_saturation(cube, random.uniform(0.85, 1.3))
            
            # Random temperature shift
            cube = self._apply_temperature(cube, random.uniform(-0.15, 0.15))
            
            # Random lift/gamma/gain for film look
            lift = random.uniform(0.0, 0.05)
            gamma = random.uniform(0.92, 1.08)
            gain = random.uniform(0.95, 1.05)
            cube = self._apply_lift_gamma_gain(cube, lift, gamma, gain)

        # --- EXISTING STYLES ---
        elif "Cinematic" in style:
            cube = self._apply_contrast_scurve(cube, amount=random.uniform(0.5, 0.9))
            teal = np.array([0.0, random.uniform(0.1, 0.3), random.uniform(0.3, 0.5)])
            orange = np.array([random.uniform(0.4, 0.6), random.uniform(0.2, 0.4), 0.0])
            cube = self._apply_split_tone(cube, teal, orange, strength=random.uniform(0.2, 0.4))
            cube = self._apply_saturation(cube, random.uniform(0.8, 1.1))

        elif "TikTok" in style:
            cube = self._apply_contrast_scurve(cube, amount=random.uniform(0.3, 0.6))
            cube = self._apply_saturation(cube, random.uniform(1.4, 1.8)) # Extreme Sat
            cube = self._apply_temperature(cube, random.uniform(-0.2, 0.2))
            cube = self._apply_lift_gamma_gain(cube, 0.0, 0.95, random.uniform(1.02, 1.1))

        elif "Vintage" in style:
            lift = random.uniform(0.05, 0.15)
            cube = self._apply_lift_gamma_gain(cube, lift, 1.1, 0.9)
            warm = np.array([0.05, 0.03, 0.0])
            cube = cube + (warm * random.uniform(0.5, 1.5))
            cube = self._apply_saturation(cube, random.uniform(0.5, 0.75))

        elif "Cyberpunk" in style:
            pink = np.array([0.4, 0.0, 0.4])
            cyan = np.array([0.0, 0.4, 0.5])
            cube = self._apply_split_tone(cube, pink, cyan, strength=random.uniform(0.6, 0.8))
            cube = self._apply_saturation(cube, 1.4)
            cube = self._apply_contrast_scurve(cube, amount=0.7)

        elif "B&W" in style:
            cube = self._apply_saturation(cube, 0.0)
            cube = self._apply_contrast_scurve(cube, amount=random.uniform(0.8, 1.4))

        # --- NEW VIBRANT STYLES ---
        
        elif "Summer Pop" in style:
            # Golden Skin, Bright Blues, High Saturation
            cube = self._apply_contrast_scurve(cube, amount=0.5)
            cube = self._apply_saturation(cube, random.uniform(1.2, 1.5))
            # Warm Gain
            cube = self._apply_lift_gamma_gain(cube, 0.0, 0.95, 1.05) 
            cube = self._apply_temperature(cube, random.uniform(0.1, 0.3)) # Always warm

        elif "Neon Tokyo" in style:
            # Deep Purple Shadows, Cyan Highlights, Night Vibe
            purple = np.array([0.2, 0.0, 0.3])
            aqua = np.array([0.0, 0.3, 0.4])
            cube = self._apply_split_tone(cube, purple, aqua, strength=0.5)
            cube = self._apply_contrast_scurve(cube, amount=0.8) # High contrast
            cube = self._apply_saturation(cube, random.uniform(1.2, 1.6))

        elif "Candy Pastel" in style:
            # Bright, Low Contrast, Pink Tint
            cube = self._apply_contrast_scurve(cube, amount=0.3) # Soft contrast
            cube = self._apply_lift_gamma_gain(cube, lift=0.05, gamma=0.9, gain=1.1) # Brighten
            cube = self._apply_saturation(cube, random.uniform(1.1, 1.3))
            # Pink Tint
            cube = cube + np.array([0.03, 0.0, 0.02]) 

        # --- NEW CLASSIC STYLES ---

        elif "Fuji Velvia" in style:
            # Nature: Crushed blacks, Vibrant Greens/Purples
            cube = self._apply_contrast_scurve(cube, amount=0.9) # Very High Contrast
            cube = self._apply_saturation(cube, random.uniform(1.2, 1.4))
            # Slight Magenta Shift for that Velvia look
            cube = cube + np.array([0.02, -0.01, 0.02])

        elif "Bleach Bypass" in style:
            # Action Movie: Silver, Desaturated, High Contrast
            cube = self._apply_saturation(cube, random.uniform(0.2, 0.4)) # Very Low Sat
            cube = self._apply_contrast_scurve(cube, amount=1.2) # Extreme Contrast
            # Silver/Metallic Tint (Cool)
            cube = self._apply_temperature(cube, -0.1)

        elif "Matrix Green" in style:
            # Stylized Digital Green
            cube = self._apply_contrast_scurve(cube, amount=0.7)
            # Green Gain, Red/Blue reduction
            green_matrix = np.array([0.9, 1.1, 0.9])
            cube = cube * green_matrix
            # Lift blacks slightly green
            cube = cube + np.array([0.0, 0.02, 0.0])
            cube = self._apply_saturation(cube, 0.8)

        return np.clip(cube, 0, 1)

    def save_cube(self, cube_data, file_path, name="RandomLUT"):
        N = cube_data.shape[0]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f'TITLE "Gen_{name}"\n')
            f.write(f'LUT_3D_SIZE {N}\n')
            f.write('DOMAIN_MIN 0.0 0.0 0.0\n')
            f.write('DOMAIN_MAX 1.0 1.0 1.0\n\n')
            for b in range(N):
                for g in range(N):
                    for r in range(N):
                        p = cube_data[r, g, b]
                        f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")

    def apply_lut_to_image_fast(self, image_array, lut_cube):
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
    
    def apply_lut_to_image_fast_uint8(self, image_array, lut_cube):
        """Apply LUT and return uint8 for display purposes."""
        result = self.apply_lut_to_image_fast(image_array, lut_cube)
        return (result * 255).astype(np.uint8)