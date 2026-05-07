import numpy as np
from PIL import Image
import os
import subprocess
import tempfile

import shutil
import time

class VideoLUTEngine:
    """Engine for extracting frames from video and applying LUT."""
    
    def __init__(self, ffmpeg_path=None):
        # 1. Start with provided path or default logic
        if ffmpeg_path:
            self.ffmpeg_path = os.path.abspath(ffmpeg_path)
        else:
            # Check bundled FFmpeg first
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_dir = os.path.dirname(script_dir)
            local_ffmpeg = os.path.join(project_dir, "bin", "ffmpeg", "ffmpeg.exe")
            
            if os.path.exists(local_ffmpeg):
                self.ffmpeg_path = local_ffmpeg
            else:
                self.ffmpeg_path = "ffmpeg"  # Fallback to PATH (might fail on Windows if not set)

        print(f"[DEBUG] VideoLUTEngine using ffmpeg: {self.ffmpeg_path}")

    def get_ffprobe_path(self):
        """Derive ffprobe path from ffmpeg path."""
        if "ffmpeg.exe" in self.ffmpeg_path:
            return self.ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
        elif "ffmpeg" in self.ffmpeg_path and os.sep in self.ffmpeg_path:
            # It's a path like /usr/bin/ffmpeg
            return self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        else:
            # It's just command "ffmpeg"
            return "ffprobe"

    def get_video_duration(self, video_path):
        """Get video duration in seconds using ffprobe. Retry on lock."""
        ffprobe_path = self.get_ffprobe_path()
        
        cmd_base = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1"
        ]
        
        # Helper to run probe
        def run_probe(path):
            try:
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                cmd = cmd_base + [path]
                # Increase timeout for fallback
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, startupinfo=startupinfo)
                return res
            except Exception as ex:
                return ex

        # Retry loop (3 attempts)
        max_retries = 3
        for i in range(max_retries):
            result = run_probe(video_path)
            
            if isinstance(result, subprocess.CompletedProcess):
                if result.returncode == 0:
                    try:
                        val = float(result.stdout.strip())
                        return val
                    except:
                        pass # Output not a float?

                # Check for permission/lock errors
                err_msg = result.stderr.lower() if result.stderr else ""
                if "permission denied" in err_msg or "access is denied" in err_msg:
                    print(f"[WARN] ffprobe permission denied (attempt {i+1}/{max_retries})...")
                    if i < max_retries - 1:
                        time.sleep(1.0) # Wait for lock to clear
                        continue
                else:
                    # Non-lock error, print and maybe retry?
                    if result.returncode != 0:
                        print(f"[ERROR] ffprobe error: {result.stderr}")
            else:
                print(f"[ERROR] ffprobe exception: {result}")
            
            # If valid result not found, sleep briefly before retry (if not last)
            if i < max_retries - 1:
                time.sleep(0.5)

        # Fallback: Try copying file to temp (sometimes bypasses lock)
        print("[WARN] ffprobe failed on direct access. Attempting fallback copy...")
        try:
            temp_copy = video_path + f".{int(time.time())}.temp"
            shutil.copy2(video_path, temp_copy)
            
            res_copy = run_probe(temp_copy)
            
            # Cleanup
            try:
                os.remove(temp_copy)
            except:
                pass
                
            if isinstance(res_copy, subprocess.CompletedProcess) and res_copy.returncode == 0:
                 return float(res_copy.stdout.strip())
            else:
                 if isinstance(res_copy, subprocess.CompletedProcess):
                      print(f"[ERROR] Copy fallback failed: {res_copy.stderr}")
        except Exception as e:
            print(f"[ERROR] Copy fallback exception: {e}")
            
        return None
    
    def extract_frame_at_time(self, video_path, time_seconds, output_path=None):
        """Extract a single frame at specified time."""
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".png")
        
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite
            "-ss", str(time_seconds),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path
        ]
        
        try:
            # On Windows, hide console
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            subprocess.run(cmd, capture_output=True, timeout=60, startupinfo=startupinfo)
            if os.path.exists(output_path):
                return Image.open(output_path)
        except Exception as e:
            print(f"[ERROR] Extracting frame failed: {e}")
        
        return None
    
    def extract_frames_auto(self, video_path):
        """
        Extract 4 frames at 20%, 40%, 60%, 80% of video duration.
        Returns list of PIL Images.
        """
        duration = self.get_video_duration(video_path)
        if duration is None:
            return None, None, None, None
        
        # Calculate timestamps
        t1 = duration * 0.20
        t2 = duration * 0.40
        t3 = duration * 0.60
        t4 = duration * 0.80
        
        # Extract frames
        frame1 = self.extract_frame_at_time(video_path, t1)
        frame2 = self.extract_frame_at_time(video_path, t2)
        frame3 = self.extract_frame_at_time(video_path, t3)
        frame4 = self.extract_frame_at_time(video_path, t4)
        
        return frame1, frame2, frame3, frame4
    
    def apply_lut_to_frame(self, frame, lut_data, engine):
        """Apply LUT to a single frame."""
        if frame is None:
            return None
        
        # Resize for preview (optional)
        frame.thumbnail((1024, 1024))
        src_arr = np.array(frame)
        
        # Handle both LUTRandomizer and ManualLUTEngine (use uint8 for display)
        if hasattr(engine, 'apply_lut_to_image_fast_uint8'):
            preview_arr = engine.apply_lut_to_image_fast_uint8(src_arr, lut_data)
        elif hasattr(engine, 'apply_lut_fast_uint8'):
            preview_arr = engine.apply_lut_fast_uint8(src_arr, lut_data)
        else:
            # Fallback for compatibility
            preview_arr = engine.apply_lut_fast(src_arr, lut_data)
            if preview_arr.dtype == np.float32:
                preview_arr = (preview_arr * 255).astype(np.uint8)
        return Image.fromarray(preview_arr)
    
    def apply_lut_to_frame_full(self, frame, lut_data, engine):
        """Apply LUT to a single frame at full resolution."""
        if frame is None:
            return None
        
        src_arr = np.array(frame)
        # Handle both LUTRandomizer and ManualLUTEngine (use uint8 for display)
        if hasattr(engine, 'apply_lut_to_image_fast_uint8'):
            preview_arr = engine.apply_lut_to_image_fast_uint8(src_arr, lut_data)
        elif hasattr(engine, 'apply_lut_fast_uint8'):
            preview_arr = engine.apply_lut_fast_uint8(src_arr, lut_data)
        else:
            # Fallback for compatibility
            preview_arr = engine.apply_lut_fast(src_arr, lut_data)
            if preview_arr.dtype == np.float32:
                preview_arr = (preview_arr * 255).astype(np.uint8)
        return Image.fromarray(preview_arr)


# ==========================================
#   VIDEO MODE UI ACTIONS
# ==========================================

import time
import time
from randomizer_stochastic_parametric import LUTRandomizer as StandardRandomizer
from randomizer_arri_logc4 import LUTRandomizer as ProRandomizer
from image_mode import ManualLUTEngine
from settings import get_grid_size, DEFAULT_LOGIC_ENGINE


class VideoModeUI:
    """UI action handlers for Video Mode tab."""
    
    def __init__(self):
        self.lut_data = None
        self.engine = None
        self.style = None
        self.size = None
    
    def auto_preview(self, video_file, style, quality, logic_engine=DEFAULT_LOGIC_ENGINE):
        """Extract 4 frames and apply random LUT (Full Resolution)."""
        if video_file is None:
            return None, None, None, None, None, None, None, None
        
        video_engine = VideoLUTEngine()
        size = get_grid_size(quality)
        
        if "ARRI" in logic_engine:
            randomizer = ProRandomizer(size=size)
        else:
            randomizer = StandardRandomizer(size=size)
            
        lut_data = randomizer.generate_unique_lut(style)
        
        # Store in state
        self.lut_data = lut_data
        self.engine = randomizer
        self.style = style
        self.size = size
        
        frame1, frame2, frame3, frame4 = video_engine.extract_frames_auto(video_file)
        
        if frame1 is None or frame2 is None or frame3 is None or frame4 is None:
            return None, None, None, None, None, None, None, None
        
        colorized1 = video_engine.apply_lut_to_frame_full(frame1.copy(), lut_data, randomizer)
        colorized2 = video_engine.apply_lut_to_frame_full(frame2.copy(), lut_data, randomizer)
        colorized3 = video_engine.apply_lut_to_frame_full(frame3.copy(), lut_data, randomizer)
        colorized4 = video_engine.apply_lut_to_frame_full(frame4.copy(), lut_data, randomizer)
        
        return frame1, colorized1, frame2, colorized2, frame3, colorized3, frame4, colorized4
    
    def grading_preview(self, video_file, quality, exp, cont, high, shad, whites, blacks, 
                        temp, tint, vib, sat, fade, cross, bleach):
        """Extract 4 frames and apply manual Color Grading LUT (Full Resolution)."""
        if video_file is None:
            return None, None, None, None, None, None, None, None
        
        video_engine = VideoLUTEngine()
        size = get_grid_size(quality)
        engine = ManualLUTEngine(size=size)
        lut_data = engine.build_lut(exp, cont, high, shad, whites, blacks, 
                                    temp, tint, vib, sat, fade, cross, bleach)
        
        # Store in state
        self.lut_data = lut_data
        self.engine = engine
        self.style = "ColorGrade"
        self.size = size
        
        frame1, frame2, frame3, frame4 = video_engine.extract_frames_auto(video_file)
        
        if frame1 is None or frame2 is None or frame3 is None or frame4 is None:
            return None, None, None, None, None, None, None, None
        
        colorized1 = video_engine.apply_lut_to_frame_full(frame1.copy(), lut_data, engine)
        colorized2 = video_engine.apply_lut_to_frame_full(frame2.copy(), lut_data, engine)
        colorized3 = video_engine.apply_lut_to_frame_full(frame3.copy(), lut_data, engine)
        colorized4 = video_engine.apply_lut_to_frame_full(frame4.copy(), lut_data, engine)
        
        return frame1, colorized1, frame2, colorized2, frame3, colorized3, frame4, colorized4
    
    def build_lut(self):
        """Build and save the .cube file from stored LUT data."""
        if self.lut_data is None:
            return None
        
        ts = int(time.time())
        safe_style = self.style.split(' ')[0].upper().replace("/", "-")
        filename = f"LUT_VIDEO_{safe_style}_{self.size}grid_{ts}.cube"
        
        os.makedirs(os.path.join("output", "video_mode"), exist_ok=True)
        out_path = os.path.join("output", "video_mode", filename)
        
        self.engine.save_cube(self.lut_data, out_path, name=f"VIDEO_{safe_style}_{ts}")
        
        return out_path

    # ==========================================
    #   MANUAL MODE (SINGLE FRAME) ACTIONS
    # ==========================================

    def get_duration(self, video_file):
        """Get video duration in seconds."""
        if video_file is None:
            return 0
        engine = VideoLUTEngine()
        dur = engine.get_video_duration(video_file)
        return dur if dur else 0

    def extract_manual_frame(self, video_file, time_sec):
        """Extract single frame at specific time."""
        if video_file is None:
            return None
        engine = VideoLUTEngine()
        frame = engine.extract_frame_at_time(video_file, time_sec)
        return frame

    def generate_auto_lut_manual(self, frame, style, quality, logic_engine=DEFAULT_LOGIC_ENGINE):
        """Generate NEW Preset/Random LUT, store it, and apply to frame."""
        if frame is None:
            return None
        
        size = get_grid_size(quality)
        if "ARRI" in logic_engine:
            randomizer = ProRandomizer(size=size)
        else:
            randomizer = StandardRandomizer(size=size)
            
        lut_data = randomizer.generate_unique_lut(style)
        
        # Store state
        self.lut_data = lut_data
        self.engine = randomizer
        self.style = style
        self.size = size
        
        return self.apply_stored_lut_manual(frame)

    def apply_stored_lut_manual(self, frame):
        """Apply the currently stored LUT to the frame (if exists)."""
        if frame is None:
            return None
        
        if self.lut_data is None:
            # No LUT generated yet, return original
            return frame
            
        # Convert PIL to numpy if needed
        import numpy as np
        if hasattr(frame, 'convert'):
             input_array = np.array(frame)
        else:
             input_array = frame
             
        # Helper to apply LUT based on engine type
        if hasattr(self.engine, 'apply_lut_to_image_fast_uint8'):
             colorized = self.engine.apply_lut_to_image_fast_uint8(input_array, self.lut_data)
        elif hasattr(self.engine, 'apply_lut_fast_uint8'):
             colorized = self.engine.apply_lut_fast_uint8(input_array, self.lut_data)
        else:
             # Fallback
             try:
                 colorized = self.engine.apply_lut_fast(input_array, self.lut_data)
                 if colorized.dtype == np.float32:
                     colorized = (colorized * 255).astype(np.uint8)
             except:
                 # Last resort fallback if engine interface is totally unexpected
                 return frame
        
        # Return PIL image for Gradio
        from PIL import Image
        return Image.fromarray(colorized)

    def manual_preview_grading(self, frame, quality, exp, cont, high, shad, whites, blacks, 
                               temp, tint, vib, sat, fade, cross, bleach):
        """Build LUT from sliders, store it, and apply to frame."""
        if frame is None:
            return None
            
        size = get_grid_size(quality)
        engine = ManualLUTEngine(size=size)
        lut_data = engine.build_lut(exp, cont, high, shad, whites, blacks, 
                                    temp, tint, vib, sat, fade, cross, bleach)
        
        # Store state
        self.lut_data = lut_data
        self.engine = engine
        self.style = "ColorGrade"
        self.size = size
        
        return self.apply_stored_lut_manual(frame)
