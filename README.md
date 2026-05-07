# LUT Colorator - Cinematic LUT Generator & Color Grading Studio

[![Windows](https://img.shields.io/badge/Platform-Windows-0078D4?style=flat-square&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-Portable%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Portable-007808?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![NVENC](https://img.shields.io/badge/Encoding-Optional%20NVENC-76B900?style=flat-square&logo=nvidia&logoColor=white)](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new)
[![Gradio](https://img.shields.io/badge/UI-Gradio-F97316?style=flat-square)](https://www.gradio.app/)
[![NumPy](https://img.shields.io/badge/Core-NumPy-013243?style=flat-square&logo=numpy&logoColor=white)](https://numpy.org/)
[![Pillow](https://img.shields.io/badge/Image-Pillow-blue?style=flat-square)](https://python-pillow.org/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

A portable Windows color-grading app for creating, previewing, exporting, and applying **3D LUT `.cube` files** to images and videos.

LUT Colorator combines stochastic preset generation, ARRI LogC4-style look creation, manual grading controls, video-frame previews, and FFmpeg-based LUT merging in one local Gradio interface.

> **Goal:** build a cinematic LUT from a target vibe or manual color grade, preview it on real images or video frames, export the `.cube`, then apply that LUT to stills or full video renders.

---

## ✨ Features

*   **🎨 Target Vibe LUT Generation:** Creates unique LUTs from creative looks such as Random, TikTok, Summer Pop, Neon Tokyo, Candy Pastel, Cinematic, Fuji Velvia, Bleach Bypass, Matrix Green, Vintage, Cyberpunk, and B&W Noir.
*   **🎛️ Manual Color Grading Suite:** Adjusts exposure, contrast, highlights, shadows, whites, blacks, temperature, tint, vibrance, saturation, fade, cross process, and bleach bypass.
*   **🪄 Auto Adjust:** Analyzes an image or video frame and estimates balanced light and color settings while leaving artistic FX controls under user control.
*   **🧠 Dual LUT Engines:** Supports a stochastic parametric engine and an ARRI LogC4-style pro engine for different creative response curves.
*   **🧊 Multi-Resolution LUT Quality:** Exports Standard 33-grid, Ultra 65-grid, or Extreme 129-grid `.cube` LUTs.
*   **🖼️ Image Preview & Export:** Generates full-resolution previews and saves graded images locally.
*   **🎞️ Video Frame Preview:** Extracts multiple frames from a video automatically, applies the generated LUT, and shows original/colorized comparisons.
*   **🎯 Manual Video Frame Selection:** Lets you select a specific timestamp, preview one frame, and fine-tune a LUT against that exact moment.
*   **🔀 Merge Mode:** Applies existing `.cube` LUT files to images or videos without rebuilding a new LUT.
*   **⚡ Optional NVIDIA NVENC:** Uses hardware encoding for H.264/H.265 video output when enabled and supported.
*   **🎬 Multiple Render Codecs:** Supports H.264, H.265, ProRes 422 Proxy, ProRes 422 HQ, ProRes 4444 XQ, and FFV1 Lossless output profiles.
*   **🌐 Local Web UI:** Runs a Gradio interface locally at `http://127.0.0.1:7860`.
*   **📦 Portable Runtime:** Designed around a bundled Python runtime, local FFmpeg, and self-contained output folders.

---

## 📦 Portable Folder Layout

A complete portable release is expected to look like this:

```text
LUT Colorator/
├── start.bat                                # One-click Windows launcher
├── install.bat                              # Portable runtime installer
├── requirements.txt                         # Python package pins
├── LICENSE                                  # Apache-2.0 license text
├── scripts/
│   └── install.ps1                          # Runtime + FFmpeg setup script
├── bin/
│   ├── python-3.13.x-embed-amd64/           # Portable Python runtime
│   └── ffmpeg/
│       ├── ffmpeg.exe                       # Portable FFmpeg
│       └── ffprobe.exe                      # Portable FFprobe
├── src/
│   ├── app.py                               # Gradio web UI and tab wiring
│   ├── image_mode.py                        # Image presets, manual grading, image save logic
│   ├── video_mode.py                        # Video frame extraction and LUT preview logic
│   ├── merge_mode.py                        # FFmpeg LUT application for images/videos
│   ├── randomizer_stochastic_parametric.py  # Standard creative LUT generator
│   ├── randomizer_arri_logc4.py             # ARRI LogC4-style pro LUT generator
│   ├── settings.py                          # Quality and logic-engine configuration
│   ├── config.ini                           # Saved app defaults
│   └── assets/
│       ├── icons/                           # UI button icons
│       └── reference_sample.png             # Auto-created fallback preview image
└── output/
    ├── preset_mode/                         # Preset-generated LUTs
    ├── manual_mode/                         # Manual grading LUTs
    ├── video_mode/                          # Video-preview LUTs
    ├── merge_mode/                          # Rendered videos and merged images
    ├── images/                              # Saved preview images
    └── temp_luts/                           # Temporary LUT copies used during FFmpeg rendering
```

> Output subfolders are created automatically when the related tool is used.

---

## 🛠️ Quick Start - Windows Portable

1.  Download or extract LUT Colorator.

2.  Keep the folder path simple, for example a short folder under `D:\AI\` or another local drive.

3.  Run the installer once if the portable Python and FFmpeg runtime folders are not already included.

4.  Open the app with the Windows launcher file.

5.  The browser opens the local Gradio interface at `http://127.0.0.1:7860`.

6.  Choose one of the main tabs:

    *   **Image Mode** for building LUTs from a still image.
    *   **Video Mode** for building LUTs while previewing video frames.
    *   **Merge Mode** for applying an existing LUT to an image or video.
    *   **Settings** for quality and engine defaults.

7.  Generate a preview, build the LUT, or render the graded media.

8.  Finished LUTs, images, and videos are saved inside `output/`.

---

## 🎮 How to Use the Web UI

### 1. Image Mode - Presets

Use **Presets** when you want LUT Colorator to design a look automatically.

| Control | Purpose |
|---|---|
| **Target Vibe** | Selects the creative style family. |
| **Reference Image** | Optional image used to preview the generated LUT. |
| **Generate LUT Full Preview** | Creates a new LUT and applies it to the preview image at full resolution. |
| **Build LUT** | Saves the current generated look as a `.cube` file. |
| **Save Image** | Saves the current preview result as an image. |

Best for fast look development, social-media color styles, filmic looks, stylized grades, and reusable `.cube` export.

### 2. Image Mode - Color Grading

Use **Color Grading** when you want direct manual control.

| Category | Controls |
|---|---|
| **Light** | Exposure, Contrast, Highlights, Shadows, Whites, Blacks |
| **Color** | Temperature, Tint, Vibrance, Saturation |
| **Additional Pro FX** | Fade, Cross Process, Bleach Bypass |

The preview updates from slider releases and image changes. **Auto Adjust** reads the current image and estimates balanced light/color values. **Reset** returns the grade to neutral. **Build LUT** saves the manual grade as a `.cube` file.

### 3. Video Mode - Auto Preview

Use **Video Mode** when the LUT should be judged against moving footage instead of only a still image.

In **Auto** mode, LUT Colorator extracts four frames from the source video around 20%, 40%, 60%, and 80% of its duration. It then displays each original frame next to a colorized version.

| Process Mode | Purpose |
|---|---|
| **Target Vibe** | Generates a new style-based LUT and previews it across multiple frames. |
| **Color Grading** | Builds a manual grade from sliders and previews it across multiple frames. |

This mode is useful for checking whether a LUT holds up across different shots, lighting changes, and scene positions.

### 4. Video Mode - Manual Frame

Use **Manual** mode when one exact video moment matters most.

1.  Upload a video.
2.  Move the frame-time slider to choose a timestamp.
3.  Extract the selected frame.
4.  Apply either **Target Vibe** or **Color Grading**.
5.  Build the final `.cube` LUT when the selected frame looks correct.

This is useful for hero shots, thumbnails, product clips, music-video keyframes, or a specific scene that defines the whole grade.

### 5. Merge Mode - Apply LUT to Image

Use the **Image** merge type to apply an existing `.cube` LUT to a still image.

| Control | Purpose |
|---|---|
| **Input Image** | Still image to process. |
| **LUT File** | Existing `.cube` LUT to apply. |
| **Output Format** | Choose PNG or JPG. |
| **Generate Preview** | Creates a preview render. |
| **Save Image** | Saves the rendered image to the output folder. |

### 6. Merge Mode - Apply LUT to Video

Use the **Video** merge type to apply an existing `.cube` LUT to a complete video render.

| Codec | Container | Best for |
|---|---:|---|
| **H.264 - Good** | `.mp4` | Fast, compatible exports. |
| **H.264 - Best** | `.mp4` | Higher-quality delivery exports. |
| **H.265 - Good** | `.mkv` | Smaller files with modern playback support. |
| **H.265 - Best** | `.mkv` | Higher-quality HEVC export. |
| **ProRes 422 Proxy** | `.mov` | Editing proxies and smooth NLE playback. |
| **ProRes 422 HQ** | `.mov` | High-quality editing handoff. |
| **ProRes 4444 XQ** | `.mov` | Maximum-quality ProRes path. |
| **FFV1 Lossless** | `.mkv` | Archival or lossless intermediate workflow. |

Enable **Hardware Acceleration (NVIDIA NVENC)** only for supported H.264/H.265 GPU encoding workflows.

### 7. Settings

The **Settings** tab controls global generation defaults.

| Setting | Options |
|---|---|
| **LUT Quality** | Standard 33 Grid, Ultra 65 Grid, Extreme 129 Grid |
| **Logic Engine** | Stochastic Parametric, ARRI LogC4 |

Settings are saved into `config.ini`. Restarting the app applies saved defaults at startup.

---

## 🧠 LUT Generation Flow

LUT Colorator follows a preview-first workflow:

```text
Start
├── Launch local Gradio interface
├── Choose Image Mode, Video Mode, Merge Mode, or Settings
├── Select LUT quality and logic engine
├── Generate a preview from a target vibe or manual grade
├── Store the generated LUT data in the active mode
├── Build a .cube file when the preview is approved
├── Optionally save the preview image
├── Optionally apply the .cube to an image or full video in Merge Mode
└── Save final files inside output/
```

---

## 🎨 Creative Preset Families

| Preset | Character |
|---|---|
| **Random** | Unique generated contrast, split-tone, saturation, temperature, and filmic lift variations. |
| **TikTok Ultra Vibrant** | Bright, high-saturation, punchy social-media color. |
| **Summer Pop** | Warm highlights, golden skin bias, bright blues, and strong saturation. |
| **Neon Tokyo** | Purple shadows, cyan highlights, night-city contrast. |
| **Candy Pastel** | Soft contrast, lifted brightness, pink tint, and gentle saturation. |
| **Cinematic Teal/Orange** | Teal shadows, warm highlights, film-style contrast. |
| **Fuji Velvia** | High contrast, vivid nature colors, green/magenta richness. |
| **Bleach Bypass** | Desaturated, gritty, high-contrast action look. |
| **Matrix Green** | Digital green cast with stylized contrast. |
| **Vintage / Retro** | Warm lift, softer saturation, faded print feel. |
| **Cyberpunk Neon** | Pink/cyan split tone with saturated futuristic contrast. |
| **B&W Noir** | Monochrome high-contrast grade. |

---

## ⚙️ Quality Modes

| Quality | Grid Size | Best for |
|---|---:|---|
| **Standard** | 33 | Fast previews and lightweight LUTs. |
| **Ultra** | 65 | Recommended balance of quality and performance. |
| **Extreme** | 129 | Maximum LUT precision with larger files and slower generation. |

Higher grid sizes can preserve smoother color transitions, especially in subtle gradients and complex grades.

---

## 🧪 Logic Engines

### Stochastic Parametric

The standard engine starts from an identity cube, adds small randomized camera-style variance, and applies creative operations such as S-curve contrast, saturation, split toning, lift/gamma/gain, and temperature shifts.

### ARRI LogC4

The pro engine converts the identity cube into a linear/log working space, applies contrast around a mid-grey pivot, performs color operations in a more filmic response model, applies highlight rolloff, and converts the result back to an sRGB-ready LUT.

Use **Stochastic Parametric** for fast, bold, highly varied creative looks. Use **ARRI LogC4** for smoother, more filmic grading behavior.

---

## 📁 Output Guide

| Folder | Contents |
|---|---|
| `output/preset_mode/` | `.cube` LUTs generated from Image Mode presets. |
| `output/manual_mode/` | `.cube` LUTs generated from Image Mode manual grading. |
| `output/video_mode/` | `.cube` LUTs generated while previewing video frames. |
| `output/images/` | Saved preview images from preset/manual image workflows. |
| `output/merge_mode/` | Rendered videos created with an existing LUT. |
| `output/merge_mode/images/` | Images rendered through Merge Mode. |
| `output/temp_luts/` | Temporary LUT copies used by FFmpeg during rendering. |

Temporary LUT files are used to avoid Windows path-escaping problems during FFmpeg filter execution.

---
