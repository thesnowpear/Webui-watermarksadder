# WebUI-Forge Watermark Adder Extension

[中文文档](README_CN.md)

A watermark extension for Stable Diffusion WebUI Forge with visual editing, real-time preview, and extractable image pack support.

## Features

- **Text Watermarks**: Create and save custom text watermarks with color, size, opacity controls
- **Image Watermarks**: Upload and manage image watermarks (supports PNG transparent background)
- **Visual Editing**: Canvas overlay with mouse-follow preview, click to place
- **Zoom & Pan**: Scroll to zoom, drag to pan the editing view, double-click to reset
- **Pixel-based Sizing**: Watermark size in pixels (1–2000px, shortest edge)
- **Shortcut Controls**:
  - Scroll wheel: Zoom image
  - Left-drag: Pan image
  - Double-click: Reset view
  - Ctrl + Scroll: Adjust watermark size (±20px)
  - Shift + Scroll: Adjust rotation angle
  - Alt + Scroll: Adjust opacity
- **Undo / Clear**: Undo last watermark or clear all
- **Dual Save Modes**:
  - Normal save: Standard PNG with watermarks
  - Extractable pack: PNG file that can be renamed to `.zip` to extract the original unwatermarked image
- **Auto Save**: Auto-save to `outputs/watermarked/` is enabled by default when generating
- **Fetch Last Image**: Automatically scan `outputs/` folder for the latest generated image (excludes `outputs/watermarked/`)

## Installation

1. Navigate to your WebUI Forge `extensions` directory
2. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/sd-webui-watermark-adder.git
   ```
3. Restart WebUI Forge

## Usage

1. Open the **Watermark Adder** tab (top-level, same level as txt2img/img2img)
2. Upload an image to the editor, or click "Fetch Last Image" to load from `outputs/`
3. Create or select a watermark from the library (left panel)
4. Move mouse over the editor — watermark follows the cursor
5. Click to place a watermark; drag to pan, scroll to zoom
6. Click **Generate** to render the final image (auto-saved to `outputs/watermarked/` by default)
7. Save as normal PNG or extractable pack

## Tech Stack

- Python 3.x + Gradio
- Pillow (PIL)
- JavaScript + HTML5 Canvas
- Polyglot file (PNG + ZIP)

## License

MIT License
