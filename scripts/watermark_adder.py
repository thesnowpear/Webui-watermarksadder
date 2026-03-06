import os
import json
import zipfile
import io
import gradio as gr
from PIL import Image, ImageDraw, ImageFont
from modules import script_callbacks
from pathlib import Path
import shutil
import time


class WatermarkManager:
    def __init__(self):
        self.extension_dir = Path(__file__).parent.parent
        self.watermarks_dir = self.extension_dir / "watermarks"
        self.images_dir = self.watermarks_dir / "images"
        self.texts_dir = self.watermarks_dir / "texts"

        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.texts_dir.mkdir(parents=True, exist_ok=True)

        self.original_image = None
        # 缓存：字体、水印图片原图
        self._font_cache = {}
        self._wm_img_cache = {}

    def list_image_watermarks(self):
        results = []
        for img_path in sorted(self.images_dir.glob("*")):
            if img_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
                results.append(str(img_path))
        return results

    def list_text_watermarks(self):
        results = []
        for text_path in sorted(self.texts_dir.glob("*.json")):
            try:
                with open(text_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['_filename'] = text_path.stem
                data['_path'] = str(text_path)
                results.append(data)
            except Exception:
                pass
        return results

    def get_text_watermark_gallery(self):
        items = []
        for data in self.list_text_watermarks():
            preview_path = self.texts_dir / f"{data['_filename']}_preview.png"
            self._create_text_preview(data, preview_path)
            items.append((str(preview_path), data['_filename']))
        return items

    def get_image_watermark_gallery(self):
        items = []
        for img_path in self.list_image_watermarks():
            name = Path(img_path).stem
            items.append((img_path, name))
        return items

    def _create_text_preview(self, watermark_data, output_path):
        img = Image.new('RGBA', (200, 100), (40, 40, 40, 255))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", min(int(watermark_data.get('font_size', 48) / 2), 40))
        except Exception:
            font = ImageFont.load_default()
        text = watermark_data.get('text', '?')
        color = watermark_data.get('color', '#FFFFFF')
        if isinstance(color, str) and color.startswith('#') and len(color) >= 7:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            a = int(255 * watermark_data.get('opacity', 0.7))
            color = (r, g, b, a)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pos = ((200 - tw) // 2, (100 - th) // 2)
        draw.text(pos, text, fill=color, font=font)
        img.save(output_path)

    def _get_font(self, size):
        """缓存字体对象避免重复加载"""
        size = max(1, int(size))
        if size not in self._font_cache:
            try:
                self._font_cache[size] = ImageFont.truetype("arial.ttf", size)
            except Exception:
                self._font_cache[size] = ImageFont.load_default()
        return self._font_cache[size]

    def _get_wm_image(self, path):
        """缓存水印原图避免重复读盘"""
        if path not in self._wm_img_cache:
            self._wm_img_cache[path] = Image.open(path).convert('RGBA')
        return self._wm_img_cache[path].copy()

    def apply_watermark_to_image(self, base_img, watermark_configs):
        if base_img is None:
            return None
        result = base_img.convert('RGBA')
        for wm in watermark_configs:
            wm_type = wm.get('type', 'text')
            x_ratio = wm.get('x', 0.5)
            y_ratio = wm.get('y', 0.5)
            size = wm.get('size', 100)
            rotation = wm.get('rotation', 0)
            opacity = wm.get('opacity', 0.7)

            x = int(x_ratio * result.width)
            y = int(y_ratio * result.height)

            if wm_type == 'text':
                text = wm.get('text', '水印')
                color = wm.get('color', '#FFFFFF')
                # size 直接就是像素字号
                scaled_font_size = max(1, int(size))
                font = self._get_font(scaled_font_size)
                if isinstance(color, str) and color.startswith('#') and len(color) >= 7:
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)
                else:
                    r, g, b = 255, 255, 255
                a = int(255 * opacity)
                bbox = font.getbbox(text)
                tw = bbox[2] - bbox[0] + 20
                th = bbox[3] - bbox[1] + 20
                txt_layer = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
                txt_draw = ImageDraw.Draw(txt_layer)
                txt_draw.text((10 - bbox[0], 10 - bbox[1]), text, fill=(r, g, b, a), font=font)
                if rotation != 0:
                    txt_layer = txt_layer.rotate(-rotation, expand=True, resample=Image.BILINEAR)
                paste_x = x - txt_layer.width // 2
                paste_y = y - txt_layer.height // 2
                result.paste(txt_layer, (paste_x, paste_y), txt_layer)

            elif wm_type == 'image':
                img_path = wm.get('path', '')
                if not img_path or not os.path.exists(img_path):
                    continue
                wm_img = self._get_wm_image(img_path)
                # size = 水印最短边的像素数
                short_edge = min(wm_img.width, wm_img.height)
                scale = max(1, size) / short_edge if short_edge > 0 else 1
                new_w = max(1, int(wm_img.width * scale))
                new_h = max(1, int(wm_img.height * scale))
                wm_img = wm_img.resize((new_w, new_h), Image.BILINEAR)
                if opacity < 1.0:
                    alpha = wm_img.split()[3]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    wm_img.putalpha(alpha)
                if rotation != 0:
                    wm_img = wm_img.rotate(-rotation, expand=True, resample=Image.BILINEAR)
                paste_x = x - wm_img.width // 2
                paste_y = y - wm_img.height // 2
                result.paste(wm_img, (paste_x, paste_y), wm_img)

        return result.convert('RGB')

    def create_extractable_image(self, watermarked_image, original_image, output_path):
        temp_watermarked = output_path.parent / "temp_watermarked.png"
        watermarked_image.save(temp_watermarked, format='PNG')
        with open(temp_watermarked, 'rb') as f:
            image_data = f.read()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            temp_original = output_path.parent / "temp_original.png"
            original_image.save(temp_original, format='PNG')
            zf.write(temp_original, arcname="original_image.png")
            temp_original.unlink()
        zip_data = zip_buffer.getvalue()
        with open(output_path, 'wb') as f:
            f.write(image_data)
            f.write(zip_data)
        temp_watermarked.unlink()


manager = WatermarkManager()


def _resolve_file_path(file_obj):
    if file_obj is None:
        return None
    if isinstance(file_obj, str):
        if os.path.exists(file_obj):
            return file_obj
        return None
    if hasattr(file_obj, 'name'):
        path = file_obj.name
        if isinstance(path, str) and os.path.exists(path):
            return path
    if isinstance(file_obj, dict):
        path = file_obj.get('name', '')
        if isinstance(path, str) and os.path.exists(path):
            return path
    return None


def _resolve_orig_name(file_obj):
    if isinstance(file_obj, str):
        return Path(file_obj).name
    if hasattr(file_obj, 'orig_name') and file_obj.orig_name:
        return file_obj.orig_name
    if hasattr(file_obj, 'name'):
        return Path(file_obj.name).name
    if isinstance(file_obj, dict):
        return Path(file_obj.get('name', 'unknown.png')).name
    return 'unknown.png'


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as watermark_tab:
        watermark_list_state = gr.State([])

        gr.Markdown("## Watermark Adder - 水印添加工具")

        with gr.Row(equal_height=False):
            # ========== 左栏：水印库 ==========
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### 水印库")

                with gr.Tabs() as wm_tabs:
                    with gr.Tab("图片水印", id="tab_img_wm"):
                        img_wm_gallery = gr.Gallery(
                            label="图片水印",
                            columns=3,
                            rows=2,
                            height=220,
                            object_fit="contain",
                            elem_id="watermark_img_gallery",
                            show_label=False,
                            allow_preview=False,
                        )
                        # 自动上传：选择文件后自动上传，无需按钮
                        upload_img_wm = gr.File(
                            label="拖放或点击上传图片水印",
                            file_types=["image"],
                            file_count="single",
                        )

                    with gr.Tab("文字水印", id="tab_txt_wm"):
                        txt_wm_gallery = gr.Gallery(
                            label="文字水印",
                            columns=3,
                            rows=2,
                            height=220,
                            object_fit="contain",
                            elem_id="watermark_txt_gallery",
                            show_label=False,
                            allow_preview=False,
                        )
                        gr.Markdown("#### 新建文字水印")
                        wm_text_input = gr.Textbox(label="水印文字", placeholder="输入水印文字...", value="© 2024")
                        with gr.Row():
                            wm_font_size = gr.Slider(minimum=10, maximum=200, value=48, step=2, label="字体大小")
                            wm_text_color = gr.ColorPicker(label="颜色", value="#FFFFFF")
                        with gr.Row():
                            wm_text_name = gr.Textbox(label="名称", placeholder="为水印命名", scale=2)
                            save_txt_wm_btn = gr.Button("保存", size="sm", scale=1)

                with gr.Row():
                    refresh_wm_btn = gr.Button("刷新水印库", size="sm")
                    deselect_wm_btn = gr.Button("取消选择", size="sm")
                with gr.Row():
                    delete_img_wm_btn = gr.Button("删除选中图片水印", size="sm")
                    delete_txt_wm_btn = gr.Button("删除选中文字水印", size="sm")

                wm_status = gr.Textbox(label="状态", interactive=False, lines=1, show_label=False)

            # ========== 中栏：编辑区 ==========
            with gr.Column(scale=2, min_width=400):
                gr.Markdown("### 编辑区")
                gr.Markdown(
                    "Ctrl+滚轮: 调整大小 | Shift+滚轮: 调整角度 | Alt+滚轮: 调整透明度",
                    elem_classes=["watermark-shortcuts-hint"]
                )

                image_editor = gr.Image(
                    label="编辑区域 - 在此图上点击添加水印",
                    type="pil",
                    interactive=True,
                    elem_id="watermark_editor",
                    height=512,
                )

                with gr.Row():
                    fetch_last_btn = gr.Button("获取上次生成的图片", size="sm", elem_id="watermark_fetch_last")
                    clear_btn = gr.Button("清除图片", size="sm")
                    undo_btn = gr.Button("撤销上一个水印", size="sm")
                    clear_wm_btn = gr.Button("清除所有水印", size="sm")

                with gr.Row():
                    wm_size_slider = gr.Slider(
                        minimum=1, maximum=2000, value=100, step=1,
                        label="水印大小 (px 最短边像素)", elem_id="watermark_size"
                    )
                    wm_rotation_slider = gr.Slider(
                        minimum=0, maximum=360, value=0, step=5,
                        label="旋转角度", elem_id="watermark_rotation"
                    )
                # 透明度滑块放在编辑区
                wm_opacity_slider = gr.Slider(
                    minimum=0.05, maximum=1.0, value=0.7, step=0.05,
                    label="水印透明度", elem_id="watermark_opacity"
                )

                watermark_info = gr.Textbox(
                    label="已添加的水印",
                    interactive=False,
                    lines=3,
                    placeholder="尚未添加水印，请先选择水印然后点击编辑区的图片添加",
                )

                # 隐藏组件
                click_coords = gr.Textbox(visible=False, elem_id="watermark_click_coords")
                selected_wm_bridge = gr.Textbox(visible=False, elem_id="watermark_selected_bridge")

            # ========== 右栏：预览与保存 ==========
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### 预览与生成")

                generate_btn = gr.Button("生成水印图片", variant="primary", size="lg")

                preview_image = gr.Image(
                    label="预览",
                    type="pil",
                    interactive=False,
                    height=400,
                )

                gr.Markdown("### 保存")
                with gr.Row():
                    save_btn = gr.Button("保存图片", variant="primary")
                    save_extract_btn = gr.Button("保存可解压包", variant="secondary")

                save_status = gr.Textbox(label="保存状态", interactive=False, lines=2)

        # ===== 事件处理 =====

        selected_img_idx = gr.State(-1)
        selected_txt_idx = gr.State(-1)

        def refresh_galleries():
            return manager.get_image_watermark_gallery(), manager.get_text_watermark_gallery()

        def auto_upload_image_watermark(file_obj):
            """文件选择后自动上传到水印库"""
            if file_obj is None:
                return gr.update(), manager.get_image_watermark_gallery()

            src_path = _resolve_file_path(file_obj)
            if src_path is None:
                return gr.update(), manager.get_image_watermark_gallery()

            orig_name = _resolve_orig_name(file_obj)
            safe_name = "".join(c for c in orig_name if c.isalnum() or c in '._- ').strip()
            if not safe_name:
                safe_name = f"watermark_{int(time.time())}.png"
            if Path(safe_name).suffix.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
                safe_name += '.png'

            save_path = manager.images_dir / safe_name
            if save_path.exists():
                stem = save_path.stem
                suffix = save_path.suffix
                save_path = manager.images_dir / f"{stem}_{int(time.time())}{suffix}"

            shutil.copy2(src_path, save_path)

            # 清空 File 组件并刷新 gallery
            return None, manager.get_image_watermark_gallery()

        def save_text_watermark(text, font_size, color, opacity, name):
            if not text or not name:
                return "请填写水印文字和名称", manager.get_text_watermark_gallery()
            data = {
                "type": "text",
                "text": text,
                "font_size": font_size,
                "color": color,
                "opacity": opacity,
                "timestamp": time.time()
            }
            save_path = manager.texts_dir / f"{name}.json"
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            preview_path = manager.texts_dir / f"{name}_preview.png"
            if preview_path.exists():
                preview_path.unlink()
            return f"已保存: {name}", manager.get_text_watermark_gallery()

        def select_image_watermark(evt: gr.SelectData):
            imgs = manager.list_image_watermarks()
            if evt.index < len(imgs):
                path = imgs[evt.index]
                name = Path(path).stem
                bridge_data = json.dumps({
                    "type": "image",
                    "path": path,
                    "ts": time.time()
                }, ensure_ascii=False)
                return f"已选择图片水印: {name}", bridge_data
            return "选择失败", ""

        def select_text_watermark(evt: gr.SelectData):
            texts = manager.list_text_watermarks()
            if evt.index < len(texts):
                data = texts[evt.index]
                bridge_data = json.dumps({
                    "type": "text",
                    "text": data.get("text", ""),
                    "font_size": data.get("font_size", 48),
                    "color": data.get("color", "#FFFFFF"),
                    "opacity": data.get("opacity", 0.7),
                    "ts": time.time()
                }, ensure_ascii=False)
                return f"已选择文字水印: {data.get('text', '?')}", bridge_data
            return "选择失败", ""

        def deselect_watermark():
            """取消选择水印"""
            bridge_data = json.dumps({"type": None, "ts": time.time()})
            return "已取消选择", bridge_data

        def add_watermark_at_position(coords_json, bridge_json, wm_list, size, rotation, opacity):
            """JS 点击坐标 + bridge 中的选中信息 -> 添加水印到列表"""
            if not coords_json:
                return wm_list, format_watermark_list(wm_list)
            try:
                coords = json.loads(coords_json)
            except Exception:
                return wm_list, format_watermark_list(wm_list)

            wm_data = {}
            if bridge_json:
                try:
                    wm_data = json.loads(bridge_json)
                except Exception:
                    pass

            if not wm_data or not wm_data.get('type'):
                return wm_list, format_watermark_list(wm_list) + "\n(请先在左侧水印库中选择一个水印)"

            wm_type = wm_data['type']
            x_ratio = coords.get('x', 0.5)
            y_ratio = coords.get('y', 0.5)

            new_wm = {
                'type': wm_type,
                'x': x_ratio,
                'y': y_ratio,
                'size': size,
                'rotation': rotation,
                'opacity': opacity,
            }

            if wm_type == 'text':
                new_wm['text'] = wm_data.get('text', '水印')
                new_wm['color'] = wm_data.get('color', '#FFFFFF')
                new_wm['font_size'] = wm_data.get('font_size', 48)
            elif wm_type == 'image':
                new_wm['path'] = wm_data.get('path', '')
            else:
                return wm_list, format_watermark_list(wm_list) + "\n(未知水印类型)"

            wm_list = list(wm_list or []) + [new_wm]
            return wm_list, format_watermark_list(wm_list)

        def format_watermark_list(wm_list):
            if not wm_list:
                return "尚未添加水印"
            lines = []
            for i, wm in enumerate(wm_list):
                if wm['type'] == 'text':
                    lines.append(f"  [{i+1}] 文字: \"{wm.get('text', '')}\" ({wm['x']:.0%}, {wm['y']:.0%}) 大小:{wm['size']}px 透明度:{wm.get('opacity', 0.7):.0%}")
                else:
                    name = Path(wm.get('path', '')).stem if wm.get('path') else '?'
                    lines.append(f"  [{i+1}] 图片: {name} ({wm['x']:.0%}, {wm['y']:.0%}) 大小:{wm['size']}px 透明度:{wm.get('opacity', 1.0):.0%}")
            return f"共 {len(wm_list)} 个水印:\n" + "\n".join(lines)

        def undo_watermark(wm_list):
            if wm_list and len(wm_list) > 0:
                wm_list = list(wm_list)[:-1]
            return wm_list, format_watermark_list(wm_list)

        def clear_watermarks():
            return [], "尚未添加水印"

        def clear_image():
            return None, None, [], "尚未添加水印"

        def generate_watermarked(img, wm_list):
            if img is None:
                return None, "请先上传或获取图片"
            if not wm_list:
                return None, "请先添加水印（选择水印后点击编辑区图片）"
            manager.original_image = img.copy()
            result = manager.apply_watermark_to_image(img, wm_list)
            return result, f"生成完成，共应用 {len(wm_list)} 个水印"

        def save_normal(img):
            if img is None:
                return "没有可保存的图片，请先生成"
            webui_root = Path(__file__).parent.parent.parent.parent
            output_dir = webui_root / "outputs" / "watermarked"
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = output_dir / f"watermarked_{ts}.png"
            img.save(path)
            return f"已保存: {path}"

        def save_extractable(img):
            if img is None or manager.original_image is None:
                return "没有可保存的图片，请先生成"
            webui_root = Path(__file__).parent.parent.parent.parent
            output_dir = webui_root / "outputs" / "watermarked"
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = output_dir / f"extractable_{ts}.png"
            manager.create_extractable_image(img, manager.original_image, path)
            return f"可解压图片包已保存: {path}\n将 .png 改为 .zip 即可解压出原图"

        def fetch_last_image():
            """从 outputs 文件夹获取最新生成的图片"""
            # WebUI 根目录: extensions/Webui-watermark-adder/ -> 上两级
            webui_root = Path(__file__).parent.parent.parent.parent
            search_dirs = [
                webui_root / "outputs" / "txt2img-images",
                webui_root / "outputs" / "img2img-images",
                webui_root / "outputs" / "txt2img-grids",
                webui_root / "outputs" / "img2img-grids",
                webui_root / "outputs" / "extras-images",
                webui_root / "outputs",
            ]
            latest_file = None
            latest_mtime = 0

            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                # 递归搜索所有图片文件
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
                    for f in search_dir.rglob(ext):
                        try:
                            mtime = f.stat().st_mtime
                            if mtime > latest_mtime:
                                latest_mtime = mtime
                                latest_file = f
                        except Exception:
                            pass

            if latest_file is None:
                return gr.update()

            try:
                img = Image.open(latest_file)
                return img
            except Exception:
                return gr.update()

        def record_img_idx(evt: gr.SelectData):
            return evt.index

        def record_txt_idx(evt: gr.SelectData):
            return evt.index

        def do_delete_img_wm(idx):
            imgs = manager.list_image_watermarks()
            if 0 <= idx < len(imgs):
                path = Path(imgs[idx])
                if path.exists():
                    path.unlink()
                return f"已删除: {path.name}", manager.get_image_watermark_gallery(), -1
            return "请先选中要删除的水印", manager.get_image_watermark_gallery(), -1

        def do_delete_txt_wm(idx):
            texts = manager.list_text_watermarks()
            if 0 <= idx < len(texts):
                data = texts[idx]
                json_path = Path(data['_path'])
                preview_path = manager.texts_dir / f"{data['_filename']}_preview.png"
                if json_path.exists():
                    json_path.unlink()
                if preview_path.exists():
                    preview_path.unlink()
                return f"已删除: {data['_filename']}", manager.get_text_watermark_gallery(), -1
            return "请先选中要删除的水印", manager.get_text_watermark_gallery(), -1

        # --- 绑定事件 ---

        refresh_wm_btn.click(fn=refresh_galleries, outputs=[img_wm_gallery, txt_wm_gallery])

        # 自动上传：File 组件 change 事件触发上传
        upload_img_wm.change(
            fn=auto_upload_image_watermark,
            inputs=[upload_img_wm],
            outputs=[upload_img_wm, img_wm_gallery]
        )

        save_txt_wm_btn.click(
            fn=save_text_watermark,
            inputs=[wm_text_input, wm_font_size, wm_text_color, wm_opacity_slider, wm_text_name],
            outputs=[wm_status, txt_wm_gallery]
        )

        # 选择水印
        img_wm_gallery.select(
            fn=select_image_watermark,
            outputs=[wm_status, selected_wm_bridge]
        )
        txt_wm_gallery.select(
            fn=select_text_watermark,
            outputs=[wm_status, selected_wm_bridge]
        )

        # 取消选择
        deselect_wm_btn.click(
            fn=deselect_watermark,
            outputs=[wm_status, selected_wm_bridge]
        )

        # 记录选中索引用于删除
        img_wm_gallery.select(fn=record_img_idx, outputs=[selected_img_idx])
        txt_wm_gallery.select(fn=record_txt_idx, outputs=[selected_txt_idx])

        delete_img_wm_btn.click(
            fn=do_delete_img_wm,
            inputs=[selected_img_idx],
            outputs=[wm_status, img_wm_gallery, selected_img_idx]
        )
        delete_txt_wm_btn.click(
            fn=do_delete_txt_wm,
            inputs=[selected_txt_idx],
            outputs=[wm_status, txt_wm_gallery, selected_txt_idx]
        )

        # JS 点击坐标 -> 添加水印（透明度从编辑区滑块读取）
        click_coords.change(
            fn=add_watermark_at_position,
            inputs=[click_coords, selected_wm_bridge, watermark_list_state,
                    wm_size_slider, wm_rotation_slider, wm_opacity_slider],
            outputs=[watermark_list_state, watermark_info]
        )

        # 撤销/清除：同时调用 JS 清理 canvas 预览
        undo_btn.click(
            fn=undo_watermark,
            inputs=[watermark_list_state],
            outputs=[watermark_list_state, watermark_info],
            _js="() => { window.watermarkUndo && window.watermarkUndo(); }"
        )
        clear_wm_btn.click(
            fn=clear_watermarks,
            outputs=[watermark_list_state, watermark_info],
            _js="() => { window.watermarkClearAll && window.watermarkClearAll(); }"
        )
        clear_btn.click(
            fn=clear_image,
            outputs=[image_editor, preview_image, watermark_list_state, watermark_info],
            _js="() => { window.watermarkClearAll && window.watermarkClearAll(); window.watermarkRemoveCanvas && window.watermarkRemoveCanvas(); }"
        )

        # 获取上次生成的图片（从 outputs 文件夹扫描）
        fetch_last_btn.click(
            fn=fetch_last_image,
            outputs=[image_editor]
        )

        generate_btn.click(
            fn=generate_watermarked,
            inputs=[image_editor, watermark_list_state],
            outputs=[preview_image, save_status]
        )

        save_btn.click(fn=save_normal, inputs=[preview_image], outputs=[save_status])
        save_extract_btn.click(fn=save_extractable, inputs=[preview_image], outputs=[save_status])

        watermark_tab.load(fn=refresh_galleries, outputs=[img_wm_gallery, txt_wm_gallery])

    return [(watermark_tab, "Watermark Adder", "watermark_adder_tab")]


script_callbacks.on_ui_tabs(on_ui_tabs)
