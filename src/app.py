import sys
import os

# Ensure path finds local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import gradio as gr
import numpy as np
from PIL import Image

from image_mode import ManualLUTEngine, ManualModeUI, PresetsEngine, save_image_local
from lut_accel import acceleration_status
from lut_common import resize_for_preview
from merge_mode import CODEC_OPTIONS, MergeModeUI
from settings import (
    DEFAULT_LOGIC_ENGINE,
    DEFAULT_PREVIEW_MAX_SIDE,
    DEFAULT_PREVIEW_QUALITY,
    DEFAULT_PREVIEW_SIZE_MODE,
    DEFAULT_QUALITY,
    DEFAULT_SAVE_IMAGE_OUTPUT_DEPTH,
    LOGIC_ENGINE_OPTIONS,
    PREVIEW_SIZE_OPTIONS,
    QUALITY_OPTIONS,
    SAVE_IMAGE_OUTPUT_DEPTH_OPTIONS,
    get_grid_size,
    save_config,
)
from video_mode import VideoLUTEngine, VideoModeUI

# === CONFIGURATION ===
STYLES = [
    "Random",
    "TikTok (Ultra Vibrant)",
    "Summer Pop (Vibrant)",
    "Neon Tokyo (Vibrant)",
    "Candy Pastel (Vibrant)",
    "Cinematic (Teal/Orange)",
    "Fuji Velvia (Nature)",
    "Bleach Bypass (Action)",
    "Matrix Green (Stylized)",
    "Vintage / Retro",
    "Cyberpunk (Neon)",
    "B&W Noir"
]



# === APPLICATION STATE / ACTIONS ===

preset_engine = PresetsEngine()
manual_ui = ManualModeUI(size=65)
video_ui = VideoModeUI()
merge_ui = MergeModeUI()


def generate_preset_preview_full(style, quality, user_img, logic_engine):
    """Generate a preset preview and store the LUT for export."""
    return preset_engine.generate_preview_full(style, quality, user_img, logic_engine)


def build_preset_lut(quality, logic_engine):
    """Build the last generated preset LUT file using export quality."""
    return preset_engine.build_lut(quality, logic_engine)


def save_preset_image_action(image):
    """Save the preset preview image."""
    return save_image_local(image, prefix="Preset_Image")


def manual_preview_full_action(
    img_input, exp, cont, high, shad, whites, blacks,
    temp, tint, vib, sat, fade, cross, bleach, quality, logic_engine,
):
    """Generate the manual color-grading preview."""
    return manual_ui.preview_full_action(
        img_input, exp, cont, high, shad, whites, blacks,
        temp, tint, vib, sat, fade, cross, bleach, quality, logic_engine,
    )


def manual_auto_full_action(img_input, tint, fade, cross, bleach, quality, logic_engine):
    """Analyze the image and update grading sliders."""
    return manual_ui.auto_full_action(img_input, tint, fade, cross, bleach, quality, logic_engine)


def manual_reset_action(img_input):
    """Reset manual grading sliders and preview."""
    return manual_ui.reset_action(img_input)


def manual_build_action(
    exp, cont, high, shad, whites, blacks,
    temp, tint, vib, sat, fade, cross, bleach, quality, logic_engine,
):
    """Build the manual grading LUT file."""
    return manual_ui.build_action(
        exp, cont, high, shad, whites, blacks,
        temp, tint, vib, sat, fade, cross, bleach, quality, logic_engine,
    )


def save_manual_image_action(image):
    """Save the manual preview image."""
    return save_image_local(image, prefix="ColorGrade_Image")


def video_build_lut(quality, logic_engine):
    """Build the last generated video LUT file using export quality."""
    return video_ui.build_lut(quality, logic_engine)


def merge_render_action(video_file, lut_file, codec, use_nvenc):
    """Render a video with the selected LUT and codec."""
    return merge_ui.render_action(video_file, lut_file, codec, use_nvenc)

# === UI CONSTRUCTION ===
with gr.Blocks() as app:
    gr.Markdown("# LUT Studio Generator (Patreon - [patreon.com/MM744](https://www.patreon.com/MM744/))")
    

    # Define global settings components once, then render them in the Settings tab.
    quality_radio = gr.Radio(choices=QUALITY_OPTIONS, value=DEFAULT_QUALITY, label="LUT Quality", render=False)
    preview_quality_radio = gr.Radio(choices=QUALITY_OPTIONS, value=DEFAULT_PREVIEW_QUALITY, label="LUT Preview Quality", render=False)
    logic_engine_radio = gr.Radio(choices=LOGIC_ENGINE_OPTIONS, value=DEFAULT_LOGIC_ENGINE, label="Logic Engine", render=False)
    preview_size_mode_radio = gr.Radio(choices=PREVIEW_SIZE_OPTIONS, value=DEFAULT_PREVIEW_SIZE_MODE, label="Preview Size", render=False)
    preview_max_side_number = gr.Number(value=DEFAULT_PREVIEW_MAX_SIDE, precision=0, label="Preview max side (px)", render=False, visible=(DEFAULT_PREVIEW_SIZE_MODE != "Original (no changes)"))
    save_image_depth_radio = gr.Radio(choices=SAVE_IMAGE_OUTPUT_DEPTH_OPTIONS, value=DEFAULT_SAVE_IMAGE_OUTPUT_DEPTH, label="Save Image Output Depth", render=False)

    with gr.Tabs():
        
        # --- TAB 1: IMAGE MODE ---
        with gr.Tab("Image Mode"):
            
            # Mode Selection
            with gr.Row():
                image_mode_radio = gr.Radio(choices=["Presets", "Color Grading"], value="Presets", label="Mode", container=False)
            
            # --- SUB-MODE: PRESETS ---
            with gr.Group(visible=True) as presets_group:
                with gr.Row():
                    with gr.Column(scale=1):
                        style_dd = gr.Dropdown(STYLES, value=STYLES[0], label="Target Vibe")
                        # quality_radio moved to Settings
                        input_img_preset = gr.Image(label="Reference Image", type="pil", height=250)
                        gen_preview_full_btn = gr.Button("Generate LUT Full Preview", icon="assets/icons/play.svg")
                        # gen_preview_fast_btn removed
                        
                        build_lut_btn = gr.Button("Build LUT", icon="assets/icons/save.svg")
                        btn_preset_save_image = gr.Button("Save Image", icon="assets/icons/save.svg")
                        dl_img_preset = gr.File(label="Download Saved Image")

                        
                    with gr.Column(scale=2):
                        res_img_preset = gr.Image(label="Preview Result", interactive=False, format="png")
                        dl_file_preset = gr.File(label="Download 3D LUT (.cube)")
                
                # gen_preview_fast_btn removed
                
                gen_preview_full_btn.click(
                    fn=generate_preset_preview_full,
                    inputs=[style_dd, preview_quality_radio, input_img_preset, logic_engine_radio],
                    outputs=[res_img_preset]
                )
                
                build_lut_btn.click(
                    fn=build_preset_lut,
                    inputs=[quality_radio, logic_engine_radio],
                    outputs=[dl_file_preset]
                )
                
                btn_preset_save_image.click(
                    fn=save_preset_image_action,
                    inputs=[res_img_preset],
                    outputs=[dl_img_preset]
                )

            # --- SUB-MODE: COLOR GRADING (MANUAL) ---
            with gr.Group(visible=False) as color_grading_group:
                gr.Markdown("### Professional Color Grading Suite — Preview quality follows Settings")
                
                with gr.Row():
                    # Left: Sliders
                    with gr.Column(scale=1):
                        
                        # === ACTION BAR ===
                        with gr.Row():
                            btn_auto = gr.Button("Auto Adjust", scale=3, icon="assets/icons/magic.svg")
                            btn_reset = gr.Button("Reset", scale=1, icon="assets/icons/refresh.svg")

                        # === LIGHT CATEGORY ===
                        gr.Markdown("LIGHT")
                        exposure = gr.Slider(-100, 100, value=0, label="Exposure")
                        contrast = gr.Slider(-100, 100, value=0, label="Contrast")
                        highlights = gr.Slider(-100, 100, value=0, label="Highlights")
                        shadows = gr.Slider(-100, 100, value=0, label="Shadows")
                        whites = gr.Slider(-100, 100, value=0, label="Whites")
                        blacks = gr.Slider(-100, 100, value=0, label="Blacks")
                        
                        # === COLOR CATEGORY ===
                        gr.Markdown("COLOR")
                        temp = gr.Slider(-100, 100, value=0, label="Temperature")
                        tint = gr.Slider(-100, 100, value=0, label="Tint")
                        vib = gr.Slider(-100, 100, value=0, label="Vibrance")
                        sat = gr.Slider(-100, 100, value=0, label="Saturation")

                        # === ADDITIONAL PRO FX ===
                        gr.Markdown("ADDITIONAL (PRO FX)")
                        fade = gr.Slider(0, 100, value=0, label="Fade (Matte Look)")
                        cross_process = gr.Slider(0, 100, value=0, label="Cross Process (Teal/Orange)")
                        bleach = gr.Slider(0, 100, value=0, label="Bleach Bypass (Gritty)")
                        
                        # SEPARATE BUTTONS
                        btn_preview_full = gr.Button("Generate LUT Full Preview", icon="assets/icons/play.svg")
                        btn_build = gr.Button("Build LUT", icon="assets/icons/save.svg")
                        # btn_preview (fast) removed
                        
                        btn_manual_save_image = gr.Button("Save Image", icon="assets/icons/save.svg")
                        dl_img_manual = gr.File(label="Download Saved Image")


                    # Right: Image Area
                    with gr.Column(scale=2):
                        with gr.Row():
                            img_input_manual = gr.Image(label="Original (Drag & Drop)", type="pil")
                            img_output_manual = gr.Image(label="Colorized Result", interactive=False, format="png")
                        
                        img_preview_large = gr.Image(label="High-Res Detail View", interactive=False, format="png")
                        dl_file_manual = gr.File(label="Download Custom .cube")

                # --- WIRING ---
                
                sliders_light = [exposure, contrast, highlights, shadows, whites, blacks]
                sliders_color = [temp, vib, sat] # Tint is separate
                sliders_all = [exposure, contrast, highlights, shadows, whites, blacks, 
                               temp, tint, vib, sat, fade, cross_process, bleach]
                
                inputs_list = [img_input_manual] + sliders_all
                outputs_list = [img_output_manual, img_preview_large]

                # 1. Auto Full Action
                btn_auto.click(
                    fn=manual_auto_full_action,
                    inputs=[img_input_manual, tint, fade, cross_process, bleach, preview_quality_radio, logic_engine_radio],
                    outputs=sliders_light + sliders_color + outputs_list
                )

                # 2. Reset Action
                btn_reset.click(
                    fn=manual_reset_action,
                    inputs=[img_input_manual],
                    outputs=sliders_all + outputs_list
                ).then(
                    fn=manual_preview_full_action,
                    inputs=inputs_list + [preview_quality_radio, logic_engine_radio],
                    outputs=outputs_list
                )

                # 3. Slider Release (Update) -> Full Preview
                for slider in sliders_all:
                    slider.release(
                        fn=manual_preview_full_action,
                        inputs=inputs_list + [preview_quality_radio, logic_engine_radio],
                        outputs=outputs_list
                    )

                # 4. Image Upload (Update Immediate) -> Full Preview
                img_input_manual.change(
                    fn=manual_preview_full_action,
                    inputs=inputs_list + [preview_quality_radio, logic_engine_radio],
                    outputs=outputs_list
                )

                # 5. Manual Refresh -> Full Preview
                # btn_preview removed
                
                
                # 6. Manual Full Refresh (Original Resolution)
                btn_preview_full.click(
                    fn=manual_preview_full_action,
                    inputs=inputs_list + [preview_quality_radio, logic_engine_radio],
                    outputs=outputs_list
                )
                
                # 7. Build LUT
                btn_build.click(
                    fn=manual_build_action,
                    inputs=sliders_all + [quality_radio, logic_engine_radio],
                    outputs=[dl_file_manual]
                )
                
                # 8. Save Image
                btn_manual_save_image.click(
                    fn=save_manual_image_action,
                    inputs=[img_output_manual],
                    outputs=[dl_img_manual]
                )
            
            # Toggle Visibility Logic
            def toggle_image_mode(mode):
                if mode == "Presets":
                    return gr.update(visible=True), gr.update(visible=False)
                else:
                    return gr.update(visible=False), gr.update(visible=True)

            image_mode_radio.change(
                fn=toggle_image_mode,
                inputs=[image_mode_radio],
                outputs=[presets_group, color_grading_group]
            )

        # --- TAB 3: VIDEO MODE ---
        with gr.Tab("Video Mode"):
            gr.Markdown("### Video Color Grading")
            
            with gr.Row():
                # Left: Controls
                with gr.Column(scale=1):
                    video_mode_radio = gr.Radio(choices=["Auto", "Manual"], value="Auto", label="Mode")
                    video_input = gr.File(label="Upload Video (.mkv, .mp4, etc.)", file_types=[".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".mpeg", ".mpg", ".m4v", ".ogv"])
                    
                    # Process Mode selection
                    video_process_radio = gr.Radio(choices=["Target Vibe", "Color Grading"], value="Target Vibe", label="Process Mode")
                    
                    # Target Vibe section (visible by default)
                    video_style_dd = gr.Dropdown(STYLES, value=STYLES[0], label="Target Vibe")
                    
                    # Color Grading section (hidden by default)
                    with gr.Group(visible=False) as video_grading_group:
                        btn_video_auto_adjust = gr.Button("Auto Adjust", icon="assets/icons/magic.svg")
                        btn_video_reset = gr.Button("Reset", icon="assets/icons/refresh.svg")
                        
                        gr.Markdown("LIGHT")
                        v_exposure = gr.Slider(-100, 100, value=0, label="Exposure")
                        v_contrast = gr.Slider(-100, 100, value=0, label="Contrast")
                        v_highlights = gr.Slider(-100, 100, value=0, label="Highlights")
                        v_shadows = gr.Slider(-100, 100, value=0, label="Shadows")
                        v_whites = gr.Slider(-100, 100, value=0, label="Whites")
                        v_blacks = gr.Slider(-100, 100, value=0, label="Blacks")
                        
                        gr.Markdown("COLOR")
                        v_temp = gr.Slider(-100, 100, value=0, label="Temperature")
                        v_tint = gr.Slider(-100, 100, value=0, label="Tint")
                        v_vib = gr.Slider(-100, 100, value=0, label="Vibrance")
                        v_sat = gr.Slider(-100, 100, value=0, label="Saturation")
                        
                        gr.Markdown("PRO FX")
                        v_fade = gr.Slider(0, 100, value=0, label="Fade (Matte)")
                        v_cross = gr.Slider(0, 100, value=0, label="Cross Process")
                        v_bleach = gr.Slider(0, 100, value=0, label="Bleach Bypass")
                    
                    
                    # video_quality_radio moved to Settings
                    
                    btn_video_generate = gr.Button("Generate New Preview", icon="assets/icons/play.svg")
                    # btn_video_generate_full removed
                    btn_video_build = gr.Button("Build LUT", icon="assets/icons/save.svg")
                    dl_file_video = gr.File(label="Download 3D LUT (.cube)")
                    
                    # Toggle visibility based on Process Mode
                    def toggle_process_mode(mode):
                        if mode == "Target Vibe":
                            return gr.update(visible=True), gr.update(visible=False)
                        else:
                            return gr.update(visible=False), gr.update(visible=True)
                    
                    video_process_radio.change(
                        fn=toggle_process_mode,
                        inputs=[video_process_radio],
                        outputs=[video_style_dd, video_grading_group]
                    )
                
                # Right: Frame Comparison
                with gr.Column(scale=3):
                    
                    # === AUTO MODE: 4-FRAME VIEW ===
                    with gr.Group(visible=True) as video_auto_group:
                        gr.Markdown("#### Frame Comparison")
                        
                        # Frame 1 (20%)
                        with gr.Row():
                            with gr.Column():
                                video_frame1_orig = gr.Image(label="Frame 1 - Original", interactive=False, height=450, format="png")
                            with gr.Column():
                                video_frame1_color = gr.Image(label="Frame 1 - Colorized", interactive=False, height=450, format="png")
                        
                        # Frame 2 (40%)
                        with gr.Row():
                            with gr.Column():
                                video_frame2_orig = gr.Image(label="Frame 2 - Original", interactive=False, height=450, format="png")
                            with gr.Column():
                                video_frame2_color = gr.Image(label="Frame 2 - Colorized", interactive=False, height=450, format="png")
                        
                        # Frame 3 (60%)
                        with gr.Row():
                            with gr.Column():
                                video_frame3_orig = gr.Image(label="Frame 3 - Original", interactive=False, height=450, format="png")
                            with gr.Column():
                                video_frame3_color = gr.Image(label="Frame 3 - Colorized", interactive=False, height=450, format="png")
                        
                        # Frame 4 (80%)
                        with gr.Row():
                            with gr.Column():
                                video_frame4_orig = gr.Image(label="Frame 4 - Original", interactive=False, height=450, format="png")
                            with gr.Column():
                                video_frame4_color = gr.Image(label="Frame 4 - Colorized", interactive=False, height=450, format="png")

                    # === MANUAL MODE: SINGLE FRAME VIEW ===
                    with gr.Group(visible=False) as video_manual_group:
                        gr.Markdown("#### Manual Frame Selection")
                        
                        # CHANGED: Video Player replaced with Large Image
                        video_frame_large = gr.Image(label="Current Frame (Large Preview)", interactive=False, height=500, format="png")
                        
                        video_time_slider = gr.Slider(0, 100, value=0, label="Select Frame Time (seconds)")
                        
                        with gr.Row():
                            with gr.Column():
                                video_manual_frame_orig = gr.Image(label="Original Frame", interactive=False, height=500, type="pil", format="png")
                            with gr.Column():
                                video_manual_frame_color = gr.Image(label="Colorized Frame", interactive=False, height=500, format="png")
            
            # Wiring for Video Mode
            video_outputs = [video_frame1_orig, video_frame1_color, 
                            video_frame2_orig, video_frame2_color,
                            video_frame3_orig, video_frame3_color,
                            video_frame4_orig, video_frame4_color]
            
            video_grading_sliders = [v_exposure, v_contrast, v_highlights, v_shadows, v_whites, v_blacks,
                                     v_temp, v_tint, v_vib, v_sat, v_fade, v_cross, v_bleach]
            
            # Wrapper to select function based on process mode (FULL RESOLUTION)
            def video_generate_wrapper(video_file, mode_radio, frame_orig, process_mode, style, preview_quality, logic_engine,
                                       exp, cont, high, shad, whites, blacks,
                                       temp, tint, vib, sat, fade, cross, bleach):
                if mode_radio == "Manual":
                    # Manual Mode: Apply Stored LUT / Grading to the single frame
                    if frame_orig is None:
                         return [gr.update()] * 8 + [None]

                    if process_mode == "Color Grading":
                        res = video_ui.manual_preview_grading(frame_orig, preview_quality, exp, cont, high, shad, whites, blacks,
                                                              temp, tint, vib, sat, fade, cross, bleach, logic_engine)
                    else:
                        res = video_ui.generate_auto_lut_manual(frame_orig, style, preview_quality, logic_engine)
                    
                    return [gr.update()] * 8 + [res]
                
                else:
                    # Auto Mode: Generate 8 images + gr.update() for manual
                    if process_mode == "Target Vibe":
                        # Standard auto_preview is now FULL res
                        res = video_ui.auto_preview(video_file, style, preview_quality, logic_engine)
                    else:
                        # Standard grading_preview is now FULL res
                        res = video_ui.grading_preview(video_file, preview_quality, exp, cont, high, shad, whites, blacks,
                                                         temp, tint, vib, sat, fade, cross, bleach, logic_engine)
                    # res is a list of 8 images
                    return list(res) + [gr.update()]
            
            
            btn_video_generate.click(
                fn=video_generate_wrapper,
                inputs=[video_input, video_mode_radio, video_manual_frame_orig, video_process_radio, video_style_dd, preview_quality_radio, logic_engine_radio] + video_grading_sliders,
                outputs=video_outputs + [video_manual_frame_color]
            )
            
            # btn_video_generate_full removed/merged calling generic wrapper (which does full)
            
            # --- AUTO ADJUST ---
            
            video_grading_slider_list = [v_exposure, v_contrast, v_highlights, v_shadows, v_whites, v_blacks,
                                         v_temp, v_tint, v_vib, v_sat, v_fade, v_cross, v_bleach]
            
            def video_auto_adjust_action(mode_radio, video_file, preview_quality, frame_orig, preview_size_mode, preview_max_side, logic_engine):
                """Analyze 4 frames (if Auto) or 1 manual frame (if Manual)."""
                
                engine = ManualLUTEngine(size=get_grid_size(preview_quality))
                
                if mode_radio == "Manual":
                    # Single Frame Analysis
                    if frame_orig is None:
                        # Return zeros for sliders, updates for frames
                        return [0]*13 + [gr.update()]*8 + [None]
                    
                    # Analyze
                    vals = engine.analyze_image_full(np.array(frame_orig))
                    exp, cont, high, shad, whites, blacks, temp, vib, sat = vals
                    
                    # Build defaults for others
                    tint, fade, cross, bleach = 0, 0, 0, 0
                    
                    # Build LUT at preview quality and store the same slider recipe for export quality builds.
                    params = (exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach)
                    lut_data = engine.build_lut(*params, logic_engine)
                    video_ui.store_manual_lut(lut_data, engine, "AutoAdjust", engine.size, params, logic_engine)
                    
                    # Apply to manual frame
                    # Convert manual frame to array for processing if needed (though engine handles it)
                    # We utilize manual_preview_grading helper to reuse logic or apply directly
                    # Better to apply directly like manual_preview_grading does
                    
                    # Convert PIL to Numpy
                    input_arr = np.array(frame_orig)
                    # Use helper from video_mode (we need to be careful with method availability, use apply_stored logic is safer but we have direct engine)
                    # Since we are using ManualLUTEngine directly here:
                    preview_arr = engine.apply_lut_fast_uint8(input_arr, lut_data)
                    frame_color = Image.fromarray(preview_arr)
                    
                    # Return: Sliders + Auto Updates + Manual Result
                    return [exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach,
                            gr.update(), gr.update(), gr.update(), gr.update(), 
                            gr.update(), gr.update(), gr.update(), gr.update(),
                            frame_color]
                    
                else:
                    # Auto Mode (4 Frames)
                    empty_result = [0] * 13 + [None] * 8 + [gr.update()]
                    if video_file is None: return empty_result
                    
                    video_engine = VideoLUTEngine()
                    frame1, frame2, frame3, frame4 = video_engine.extract_frames_auto(video_file)
                    if frame1 is None: return empty_result
                    
                    results = []
                    for frame in [frame1, frame2, frame3, frame4]:
                        vals = engine.analyze_image_full(np.array(frame))
                        results.append(vals)
                    
                    avg_vals = []
                    for i in range(9):
                        avg = sum(r[i] for r in results) / 4
                        avg_vals.append(int(avg))
                    
                    exp, cont, high, shad, whites, blacks, temp, vib, sat = avg_vals
                    # Defaults
                    tint, fade, cross, bleach = 0, 0, 0, 0
                    
                    params = (exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach)
                    lut_data = engine.build_lut(*params, logic_engine)
                    video_ui.store_manual_lut(lut_data, engine, "AutoAdjust", engine.size, params, logic_engine)
                    
                    # Apply
                    c1 = video_engine.apply_lut_to_frame(frame1.copy(), lut_data, engine)
                    c2 = video_engine.apply_lut_to_frame(frame2.copy(), lut_data, engine)
                    c3 = video_engine.apply_lut_to_frame(frame3.copy(), lut_data, engine)
                    c4 = video_engine.apply_lut_to_frame(frame4.copy(), lut_data, engine)
                    
                    frame1 = resize_for_preview(frame1, preview_size_mode, preview_max_side)
                    frame2 = resize_for_preview(frame2, preview_size_mode, preview_max_side)
                    frame3 = resize_for_preview(frame3, preview_size_mode, preview_max_side)
                    frame4 = resize_for_preview(frame4, preview_size_mode, preview_max_side)
                    
                    return [exp, cont, high, shad, whites, blacks, temp, tint, vib, sat, fade, cross, bleach,
                            frame1, c1, frame2, c2, frame3, c3, frame4, c4,
                            gr.update()]
            
            btn_video_auto_adjust.click(
                fn=video_auto_adjust_action,
                inputs=[video_mode_radio, video_input, preview_quality_radio, video_manual_frame_orig, preview_size_mode_radio, preview_max_side_number, logic_engine_radio],
                outputs=video_grading_slider_list + video_outputs + [video_manual_frame_color]
            )
            
            # --- WIRING FOR MANUAL MODE ---

            # Toggle Auto/Manual Groups
            def toggle_video_mode(mode):
                if mode == "Manual":
                    return gr.update(visible=False), gr.update(visible=True)
                else:
                    return gr.update(visible=True), gr.update(visible=False)

            video_mode_radio.change(
                fn=toggle_video_mode,
                inputs=[video_mode_radio],
                outputs=[video_auto_group, video_manual_group]
            )

            # Update Slider Range when video loaded
            def update_slider_range(video_file):
                dur = video_ui.get_duration(video_file)
                # Ensure duration is at least 1.0 to prevent slider range issues.
                if dur is None or dur <= 0:
                    dur = 1.0
                first_frame = video_ui.extract_manual_frame(video_file, 0) if video_file else None
                return gr.update(maximum=dur, value=0), first_frame, first_frame
            
            video_input.change(
                fn=update_slider_range,
                inputs=[video_input],
                outputs=[video_time_slider, video_manual_frame_orig, video_frame_large]
            )

            # Manual Frame Extraction
            def manual_extract_action(video_file, time_val):
                frame = video_ui.extract_manual_frame(video_file, time_val)
                return frame, frame # Update both small and large

            # Slider release triggers extraction (Python)
            video_time_slider.release(
                fn=manual_extract_action,
                inputs=[video_input, video_time_slider],
                outputs=[video_manual_frame_orig, video_frame_large]
            )

            preview_size_mode_radio.change(
                fn=manual_extract_action,
                inputs=[video_input, video_time_slider],
                outputs=[video_manual_frame_orig, video_frame_large],
                show_progress=False,
            )
            preview_max_side_number.change(
                fn=manual_extract_action,
                inputs=[video_input, video_time_slider],
                outputs=[video_manual_frame_orig, video_frame_large],
                show_progress=False,
            )

            # --- MANUAL PREVIEW HANDLERS ---

            # 1. APPLY STORED / SLIDERS (Triggered by frame change or sliders)
            def manual_apply_wrapper(mode_radio, frame_orig, process_mode, preview_quality,
                                     logic_engine,
                                     exp, cont, high, shad, whites, blacks,
                                     temp, tint, vib, sat, fade, cross, bleach):
                if mode_radio != "Manual" or frame_orig is None:
                    return gr.update()
                
                if process_mode == "Color Grading":
                    # For grading, "Apply" means build from current sliders
                    return video_ui.manual_preview_grading(frame_orig, preview_quality, exp, cont, high, shad, whites, blacks,
                                                           temp, tint, vib, sat, fade, cross, bleach, logic_engine)
                else:
                    # For Target Vibe, "Apply" means use stored LUT (do not generate new)
                    return video_ui.apply_stored_lut_manual(frame_orig)

            # Bindings
            manual_trigger_inputs_apply = [video_mode_radio, video_manual_frame_orig, video_process_radio, preview_quality_radio, logic_engine_radio] + video_grading_sliders

            # Frame Change -> Apply Stored (Target Vibe) or Sliders (Grading)
            video_manual_frame_orig.change(
                fn=manual_apply_wrapper,
                inputs=manual_trigger_inputs_apply,
                outputs=[video_manual_frame_color]
            )
            
            # Process Mode Change -> Apply Stored / Grading
            video_process_radio.change(fn=manual_apply_wrapper, inputs=manual_trigger_inputs_apply, outputs=[video_manual_frame_color])
            
            # Preview Quality Change -> Apply Stored / Grading
            preview_quality_radio.change(fn=manual_apply_wrapper, inputs=manual_trigger_inputs_apply, outputs=[video_manual_frame_color])

            # Slider changes use the same wrapper for both Auto and Manual video modes.
            
            for slider in video_grading_slider_list:
                slider.release(
                    fn=video_generate_wrapper,
                    inputs=[video_input, video_mode_radio, video_manual_frame_orig, video_process_radio, video_style_dd, preview_quality_radio, logic_engine_radio] + video_grading_sliders,
                    outputs=video_outputs + [video_manual_frame_color]
                )
            
            # Reset Action
            def video_reset_action():
                return [0] * 13
            
            btn_video_reset.click(
                fn=video_reset_action,
                inputs=[],
                outputs=video_grading_slider_list
            ).then(
                fn=video_generate_wrapper,
                inputs=[video_input, video_mode_radio, video_manual_frame_orig, video_process_radio, video_style_dd, preview_quality_radio, logic_engine_radio] + video_grading_sliders,
                outputs=video_outputs + [video_manual_frame_color]
            ).then(
                # Also reset manual preview
                fn=manual_apply_wrapper,
                inputs=manual_trigger_inputs_apply,
                outputs=[video_manual_frame_color]
            )
            
            btn_video_build.click(
                fn=video_build_lut,
                inputs=[quality_radio, logic_engine_radio],
                outputs=[dl_file_video]
            )
        
        # --- TAB 4: MERGE MODE ---
        with gr.Tab("Merge Mode"):
            
            # Merge Type Selection
            with gr.Row():
                merge_type_radio = gr.Radio(choices=["Image", "Video"], value="Image", label="Merge Type", container=False)
            
            # === IMAGE MERGE GROUP ===
            with gr.Group(visible=True) as merge_image_group:
                gr.Markdown("### Apply LUT to Image")
                
                with gr.Row():
                    # Left Column: Inputs & Settings
                    with gr.Column(scale=1):
                        gr.Markdown("#### 1. Input Image")
                        merge_image_input = gr.Image(label="Upload Image", type="filepath", height=300)
                        
                        gr.Markdown("#### 2. LUT & Settings")
                        merge_lut_input_img = gr.File(label="Upload .cube LUT File", file_types=[".cube"])
                        
                        merge_image_format = gr.Radio(
                            choices=["PNG", "JPG"], 
                            value="PNG", 
                            label="Output Format",
                            interactive=True
                        )
                        
                        with gr.Row():
                            btn_merge_image_preview = gr.Button("Generate Preview", icon="assets/icons/play.svg", variant="secondary")
                            btn_merge_image_save = gr.Button("Save Image", icon="assets/icons/save.svg", variant="primary")
                        
                        merge_image_status = gr.Textbox(label="Status", lines=2, interactive=False)

                    # Right Column: Preview
                    with gr.Column(scale=2):
                        gr.Markdown("#### Result Preview")
                        merge_image_preview_res = gr.Image(label="Preview Result", interactive=False, height=600, format="png")
                        merge_image_output = gr.File(label="Download Saved Image")
                
                # Wiring
                btn_merge_image_preview.click(
                    fn=merge_ui.render_image_preview_action,
                    inputs=[merge_image_input, merge_lut_input_img],
                    outputs=[merge_image_preview_res]
                )
                
                btn_merge_image_save.click(
                    fn=merge_ui.render_image_action,
                    inputs=[merge_image_input, merge_lut_input_img, merge_image_format],
                    outputs=[merge_image_output, merge_image_status]
                )

            # === VIDEO MERGE GROUP ===
            with gr.Group(visible=False) as merge_video_group:
                gr.Markdown("### Apply LUT to Video")
                
                with gr.Row():
                    # Left Column: Inputs
                    with gr.Column(scale=1):
                        gr.Markdown("#### 1. Input Video")
                        merge_video_input = gr.File(
                            label="Upload Video", 
                            file_types=[".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".mpeg", ".mpg", ".m4v", ".ogv"]
                        )
                        
                        gr.Markdown("#### 2. LUT & Settings")
                        merge_lut_input_vid = gr.File(
                            label="Upload .cube LUT File",
                            file_types=[".cube"]
                        )
                        
                        merge_codec_radio = gr.Radio(
                            choices=CODEC_OPTIONS, 
                            value=CODEC_OPTIONS[0], 
                            label="Output Codec"
                        )
                        merge_nvenc_checkbox = gr.Checkbox(
                            label="Hardware Acceleration (NVIDIA NVENC)",
                            value=False,
                            info="Uses GPU for faster encoding (H.264/H.265 only)"
                        )
                        
                        btn_merge_render = gr.Button("Start Render", icon="assets/icons/play.svg", variant="primary")

                    # Right Column: Output
                    with gr.Column(scale=1):
                        gr.Markdown("#### Render Status")
                        merge_status = gr.Textbox(label="Log", lines=10, interactive=False)
                        merge_output_file = gr.File(label="Download Rendered Video")
                
                # Wiring
                btn_merge_render.click(
                    fn=merge_render_action,
                    inputs=[merge_video_input, merge_lut_input_vid, merge_codec_radio, merge_nvenc_checkbox],
                    outputs=[merge_output_file, merge_status]
                )
            
            # Toggle Visibility Logic for Merge Mode
            def toggle_merge_mode(mode):
                if mode == "Image":
                    return gr.update(visible=True), gr.update(visible=False)
                else:
                    return gr.update(visible=False), gr.update(visible=True)

            merge_type_radio.change(
                fn=toggle_merge_mode,
                inputs=[merge_type_radio],
                outputs=[merge_image_group, merge_video_group]
            )

        # --- TAB 5: SETTINGS ---
        with gr.Tab("Settings"):
            gr.Markdown("### Application Settings")
            gr.Markdown(
                "Changes apply immediately to the next preview or build. "
                "The button is only for explicitly re-saving the same values."
            )
            quality_radio.render()
            preview_quality_radio.render()
            preview_size_mode_radio.render()
            preview_max_side_number.render()
            save_image_depth_radio.render()
            logic_engine_radio.render()

            def toggle_preview_size_number(mode):
                return gr.update(visible=("Original" not in str(mode)))

            btn_save_settings = gr.Button("Save / Apply Settings", icon="assets/icons/save.svg")
            settings_status = gr.Textbox(
                label="Status",
                interactive=False,
                visible=True,
                lines=7,
                value=(
                    "Current settings are active. Next preview/build uses the selected values.\n"
                    f"LUT Quality: {DEFAULT_QUALITY}\n"
                    f"LUT Preview Quality: {DEFAULT_PREVIEW_QUALITY}\n"
                    f"Preview Size: {DEFAULT_PREVIEW_SIZE_MODE}\n"
                    f"Preview max side: {DEFAULT_PREVIEW_MAX_SIDE}px\n"
                    f"Engine: {DEFAULT_LOGIC_ENGINE}\n"
                    f"Acceleration: {acceleration_status()}"
                ),
            )

            def apply_settings_live(qual, preview_qual, logic, preview_size_mode, preview_max_side, save_image_depth):
                try:
                    preview_max_side = int(float(preview_max_side))
                except (TypeError, ValueError):
                    preview_max_side = DEFAULT_PREVIEW_MAX_SIDE
                if preview_max_side <= 0:
                    preview_max_side = DEFAULT_PREVIEW_MAX_SIDE
                save_config(qual, preview_qual, logic, preview_size_mode, preview_max_side, save_image_depth)
                preview_size_desc = "original size" if "Original" in str(preview_size_mode) else f"up to {preview_max_side}px longest side"
                return (
                    "Settings applied live and saved. No restart needed.\n"
                    f"Next Build LUT uses: {qual}\n"
                    f"Next preview uses LUT Preview Quality: {preview_qual}\n"
                    f"Next preview size uses: {preview_size_desc}\n"
                    f"Next generated look uses engine: {logic}\n"
                    f"Acceleration: {acceleration_status()}"
                )

            settings_inputs = [quality_radio, preview_quality_radio, logic_engine_radio, preview_size_mode_radio, preview_max_side_number, save_image_depth_radio]
            btn_save_settings.click(
                fn=apply_settings_live,
                inputs=settings_inputs,
                outputs=[settings_status]
            )
            for settings_component in settings_inputs:
                settings_component.change(
                    fn=apply_settings_live,
                    inputs=settings_inputs,
                    outputs=[settings_status],
                    show_progress=False,
                )
            preview_size_mode_radio.change(
                fn=toggle_preview_size_number,
                inputs=[preview_size_mode_radio],
                outputs=[preview_max_side_number],
                show_progress=False,
            )

if __name__ == "__main__":
    os.makedirs("output", exist_ok=True)
    print("Launching LUT Studio Generator...")
    app.queue().launch(server_name="127.0.0.1", inbrowser=True, theme=gr.themes.Ocean())
