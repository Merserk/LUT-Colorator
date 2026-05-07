"""
Merge Mode Engine for AI Cinematic LUT Generator
Applies .cube LUT files to videos using FFmpeg.
"""

import os
import subprocess
import shutil
import time
from PIL import Image

class MergeModeEngine:
    """Engine for applying LUT files to videos using FFmpeg."""
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
    
    def _find_ffmpeg(self):
        """Find ffmpeg executable."""
        # Check bundled FFmpeg first
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(current_dir)
        local_ffmpeg = os.path.join(project_dir, "bin", "ffmpeg", "ffmpeg.exe")
        
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
        
        # Fall back to system PATH
        return "ffmpeg"
    
    def get_codec_settings(self, codec_name, use_nvenc=False):
        """Get FFmpeg codec settings based on selection."""
        codecs = {
            # H.264 Options
            "H.264 - Good (MP4)": {
                "vcodec": "h264_nvenc" if use_nvenc else "libx264",
                "preset": "p4" if use_nvenc else "medium",
                "crf": "23" if not use_nvenc else None,
                "cq": "23" if use_nvenc else None,
                "ext": ".mp4",
                "extra": ["-pix_fmt", "yuv420p"]
            },
            "H.264 - Best (MP4)": {
                "vcodec": "h264_nvenc" if use_nvenc else "libx264",
                "preset": "p7" if use_nvenc else "slow",
                "crf": "18" if not use_nvenc else None,
                "cq": "18" if use_nvenc else None,
                "ext": ".mp4",
                "extra": ["-pix_fmt", "yuv420p"]
            },
            # H.265 Options
            "H.265 - Good (MKV)": {
                "vcodec": "hevc_nvenc" if use_nvenc else "libx265",
                "preset": "p4" if use_nvenc else "medium",
                "crf": "25" if not use_nvenc else None,
                "cq": "25" if use_nvenc else None,
                "ext": ".mkv",
                "extra": ["-pix_fmt", "yuv420p"]
            },
            "H.265 - Best (MKV)": {
                "vcodec": "hevc_nvenc" if use_nvenc else "libx265",
                "preset": "p7" if use_nvenc else "slow",
                "crf": "20" if not use_nvenc else None,
                "cq": "20" if use_nvenc else None,
                "ext": ".mkv",
                "extra": ["-pix_fmt", "yuv420p"]
            },
            # ProRes Options (no NVENC support)
            "ProRes 422 Proxy (MOV)": {
                "vcodec": "prores_ks",
                "profile": "0",  # Proxy
                "ext": ".mov",
                "extra": ["-pix_fmt", "yuv422p10le"]
            },
            "ProRes 422 HQ (MOV)": {
                "vcodec": "prores_ks",
                "profile": "3",  # 422 HQ
                "ext": ".mov",
                "extra": ["-pix_fmt", "yuv422p10le"]
            },
            "ProRes 4444 XQ (MOV)": {
                "vcodec": "prores_ks",
                "profile": "5",  # 4444 XQ
                "ext": ".mov",
                "extra": ["-pix_fmt", "yuva444p10le"]
            },
            # FFV1 Lossless
            "FFV1 Lossless (MKV)": {
                "vcodec": "ffv1",
                "level": "3",
                "ext": ".mkv",
                "extra": ["-pix_fmt", "yuv444p10le", "-coder", "1", "-context", "1", "-slicecrc", "1"]
            }
        }
        return codecs.get(codec_name, codecs["H.264 - Good (MP4)"])
    
    def render_video(self, input_video, lut_file, codec_name, use_nvenc=False):
        """Apply LUT to video and render with selected codec."""
        if input_video is None or lut_file is None:
            return None, "Please provide both video and LUT file."
        
        # Get input path
        if hasattr(input_video, 'name'):
            input_path = input_video.name
        else:
            input_path = input_video
        
        # Get LUT path
        if hasattr(lut_file, 'name'):
            lut_path = lut_file.name
        else:
            lut_path = lut_file
        
        # Verify files exist
        if not os.path.exists(input_path):
            return None, f"Input video not found: {input_path}"
        if not os.path.exists(lut_path):
            return None, f"LUT file not found: {lut_path}"
        
        # Get codec settings
        codec = self.get_codec_settings(codec_name, use_nvenc)
        
        # Generate output filename
        ts = int(time.time())
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{base_name}_LUT_{ts}{codec['ext']}"
        
        os.makedirs(os.path.join("output", "merge_mode"), exist_ok=True)
        output_path = os.path.join("output", "merge_mode", output_filename)
        # Copy LUT to local folder to avoid Windows path escaping issues in FFmpeg
        # Move to output/temp_luts to keep root clean
        luts_dir = os.path.join("output", "temp_luts")
        os.makedirs(luts_dir, exist_ok=True)
        lut_filename = f"{ts}_{os.path.basename(lut_path)}"
        local_lut_path = os.path.join(luts_dir, lut_filename)
        shutil.copy2(lut_path, local_lut_path)
        # Use relative path with forward slashes for FFmpeg
        lut_path_filter = f"output/temp_luts/{lut_filename}".replace("\\", "/")
        
        # Build FFmpeg command using filter_complex with explicit mapping
        # This pattern is more reliable for LUT application with hardware acceleration
        cmd = [
            self.ffmpeg_path,
            "-strict", "experimental",
            "-hide_banner",
            "-threads", "0",
        ]
        
        # Input file
        cmd.extend(["-i", input_path])
        
        # Video codec
        cmd.extend(["-c:v", codec["vcodec"]])
        
        # Add NVENC-specific options
        if use_nvenc and codec["vcodec"] in ["h264_nvenc", "hevc_nvenc"]:
            cmd.extend(["-b_ref_mode", "0"])
            # Use bitrate mode for NVENC (more compatible than CQ in some cases)
            cmd.extend(["-b:v", "20000k"])
        
        # Add codec-specific options
        if "preset" in codec:
            cmd.extend(["-preset", codec["preset"]])
        if not use_nvenc:
            # CRF only for software encoding
            if "crf" in codec and codec["crf"]:
                cmd.extend(["-crf", codec["crf"]])
        if "profile" in codec:
            cmd.extend(["-profile:v", codec["profile"]])
        if "level" in codec:
            cmd.extend(["-level", codec["level"]])
        
        # Use filter_complex with explicit stream mapping (more reliable)
        # Don't use quotes around the path - subprocess handles escaping properly
        filter_expr = f"[0:v]lut3d=file={lut_path_filter}[out]"
        cmd.extend(["-filter_complex", filter_expr])
        cmd.extend(["-map", "[out]"])
        
        # Copy audio stream (map all audio if present)
        cmd.extend(["-c:a", "copy", "-map", "a?"])
        
        # Pixel format and scaling flags
        if "extra" in codec:
            cmd.extend(codec["extra"])
        cmd.extend(["-sws_flags", "spline"])
        
        # Overwrite output
        cmd.extend(["-y", output_path])
        
        nvenc_status = " (NVENC)" if use_nvenc else ""
        print(f"[MergeMode] Running{nvenc_status}: {' '.join(cmd)}")
        
        try:
            # Hide console window on Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo
            )
            
            if result.returncode == 0:
                return output_path, f"Render complete!{nvenc_status}\nOutput: {output_filename}"
            else:
                error_msg = result.stderr[:500] if result.stderr else "Unknown error"
                return None, f"Render failed:\n{error_msg}"
                
        except FileNotFoundError:
            return None, "FFmpeg not found. Please install FFmpeg or add it to bin/ folder."
        except Exception as e:
            return None, f"Error: {str(e)}"
        finally:
            # Cleanup temp LUT
            if os.path.exists(local_lut_path):
                try:
                    os.remove(local_lut_path)
                except:
                    pass
    
    def render_image(self, input_image, lut_file, output_format):
        """Apply LUT to image using FFmpeg."""
        if input_image is None or lut_file is None:
            return None, "Please provide both image and LUT file."
            
        # Get paths
        if hasattr(input_image, 'name'):
            input_path = input_image.name
        else:
            input_path = input_image
            
        if hasattr(lut_file, 'name'):
            lut_path = lut_file.name
        else:
            lut_path = lut_file
            
        # Verify
        if not os.path.exists(input_path):
            return None, f"Input image not found: {input_path}"
        if not os.path.exists(lut_path):
            return None, f"LUT file not found: {lut_path}"
            
        # Generate output filename
        ts = int(time.time())
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        ext = ".jpg" if "JPG" in output_format else ".png"
        output_filename = f"{base_name}_LUT_{ts}{ext}"
        
        os.makedirs(os.path.join("output", "merge_mode", "images"), exist_ok=True)
        output_path = os.path.join("output", "merge_mode", "images", output_filename)
        
        # Prepare LUT (copy to local to avoid path issues)
        luts_dir = os.path.join("output", "temp_luts")
        os.makedirs(luts_dir, exist_ok=True)
        lut_filename = f"{ts}_{os.path.basename(lut_path)}"
        local_lut_path = os.path.join(luts_dir, lut_filename)
        shutil.copy2(lut_path, local_lut_path)
        lut_path_filter = f"output/temp_luts/{lut_filename}".replace("\\", "/")
        
        # Build command
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-i", input_path,
        ]
        
        # Filter
        filter_expr = f"[0:v]lut3d=file={lut_path_filter}[out]"
        cmd.extend(["-filter_complex", filter_expr, "-map", "[out]"])
        
        # Output options
        if ext == ".jpg":
            # high quality jpg
            cmd.extend(["-q:v", "2"]) 
        else:
            # png compression
            cmd.extend(["-compression_level", "3"])
            
        cmd.extend(["-y", output_path])
        
        print(f"[MergeMode] Rendering Image: {' '.join(cmd)}")
        
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo
            )
            
            if result.returncode == 0:
                return output_path, f"Image Saved!\n{output_filename}"
            else:
                 error_msg = result.stderr[:500] if result.stderr else "Unknown error"
                 return None, f"Render failed:\n{error_msg}"
        except Exception as e:
            return None, f"Error: {str(e)}"
        finally:
             if os.path.exists(local_lut_path):
                 try:
                     os.remove(local_lut_path)
                 except:
                     pass


class MergeModeUI:
    """UI action handlers for Merge Mode tab."""
    
    def __init__(self):
        self.engine = MergeModeEngine()
    
    def render_action(self, video_file, lut_file, codec, use_nvenc):
        """Start the video render process."""
        output_path, message = self.engine.render_video(video_file, lut_file, codec, use_nvenc)
        return output_path, message

    def render_image_action(self, input_image, lut_file, output_format):
        """Start the image render process."""
        output_path, message = self.engine.render_image(input_image, lut_file, output_format)
        return output_path, message

    def render_image_preview_action(self, input_image, lut_file):
        """Generate preview for image merge (returns image path only)."""
        # Force PNG for preview quality or just use same pipeline
        output_path, message = self.engine.render_image(input_image, lut_file, "PNG")
        # Return output_path for the Image component, message ignored/logged
        return output_path


# Available codec options for UI
CODEC_OPTIONS = [
    "H.264 - Good (MP4)",
    "H.264 - Best (MP4)",
    "H.265 - Good (MKV)",
    "H.265 - Best (MKV)",
    "ProRes 422 Proxy (MOV)",
    "ProRes 422 HQ (MOV)",
    "ProRes 4444 XQ (MOV)",
    "FFV1 Lossless (MKV)"
]
