import os
import json
import zipfile
import io
import base64
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

        self.current_watermarks = []
        self.original_image = None

    def list_image_watermarks(self):
        """列出图片水印文件夹中的所有图片"""
        results = []
        for img_path in sorted(self.images_dir.glob("*")):
            if img_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
                results.append(str(img_path))
        return results

    def list_text_watermarks(self):
        """列出文字水印配置"""
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
        """为文字水印生成预览图列表"""
        items = []
        for data in self.list_text_watermarks():
            preview_path = self.texts_dir / f"{data['_filename']}_preview.png"
            self._create_text_preview(data, preview_path)
            items.append((str(preview_path), data['_filename']))
        return items

    def get_image_watermark_gallery(self):
        """图片水印列表"""
        items = []
        for img_path in self.list_image_watermarks():
            name = Path(img_path).stem
            items.append((img_path, name))
        return items

    def _create_text_preview(self, watermark_data, output_path):
        """创建文字水印预览图"""
        img = Image.new('RGBA', (200, 100), (40, 40, 40, 255))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", min(int(watermark_data.get('font_size', 48) / 2), 40))
        except Exception:
            font = ImageFont.load_default()

        text = watermark_data.get('text', '?')
        color = watermark_data.get('color', '#FFFFFF')

        if color.startswith('#') and len(color) >= 7:
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

    def apply_watermark_to_image(self, base_img, watermark_configs):
        """将水印应用到图片上 (PIL 服务端渲染)"""
        if base_img is None:
            return None

        result = base_img.convert('RGBA')

        for wm in watermark_configs:
            wm_type = wm.get('type', 'text')
            x_ratio = wm.get('x', 0.5)
            y_ratio = wm.get('y', 0.5)
            size = wm.get('size', 100)
            rotation = wm.get('rotation', 0)

            x = int(x_ratio * result.width)
            y = int(y_ratio * result.height)

            if wm_type == 'text':
                text = wm.get('text', '水印')
                color = wm.get('color', '#FFFFFF')
                opacity = wm.get('opacity', 0.7)
                font_size = wm.get('font_size', 48)

                # 按 size 比例缩放字体
                scaled_font_size = int(font_size * size / 100)
                try:
                    font = ImageFont.truetype("arial.ttf", scaled_font_size)
                except Exception:
                    font = ImageFont.load_default()

                if color.startswith('#') and len(color) >= 7:
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)
                else:
                    r, g, b = 255, 255, 255
                a = int(255 * opacity)

                # 创建文字水印图层
                bbox_img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
                bbox_draw = ImageDraw.Draw(bbox_img)
                bbox = bbox_draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0] + 20
                th = bbox[3] - bbox[1] + 20

                txt_layer = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
                txt_draw = ImageDraw.Draw(txt_layer)
                txt_draw.text((10 - bbox[0], 10 - bbox[1]), text, fill=(r, g, b, a), font=font)

                if rotation != 0:
                    txt_layer = txt_layer.rotate(-rotation, expand=True, resample=Image.BICUBIC)

                paste_x = x - txt_layer.width // 2
                paste_y = y - txt_layer.height // 2
                result.paste(txt_layer, (paste_x, paste_y), txt_layer)

            elif wm_type == 'image':
                img_path = wm.get('path', '')
                opacity = wm.get('opacity', 1.0)
                if not img_path or not os.path.exists(img_path):
                    continue

                wm_img = Image.open(img_path).convert('RGBA')

                # 按 size 缩放
                scale = size / 100.0
                new_w = max(1, int(wm_img.width * scale))
                new_h = max(1, int(wm_img.height * scale))
                wm_img = wm_img.resize((new_w, new_h), Image.LANCZOS)

                # 应用透明度
                if opacity < 1.0:
                    alpha = wm_img.split()[3]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    wm_img.putalpha(alpha)

                if rotation != 0:
                    wm_img = wm_img.rotate(-rotation, expand=True, resample=Image.BICUBIC)

                paste_x = x - wm_img.width // 2
                paste_y = y - wm_img.height // 2
                result.paste(wm_img, (paste_x, paste_y), wm_img)

        return result.convert('RGB')

    def create_extractable_image(self, watermarked_image, original_image, output_path):
        """创建可解压的图片包"""
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


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as watermark_tab:
        # 全局状态
        watermark_list_state = gr.State([])  # 当前添加的水印配置列表
        selected_wm_type = gr.State("text")  # 当前选中的水印类型
        selected_wm_data = gr.State({})  # 当前选中的水印数据

        gr.Markdown("## Watermark Adder - 水印添加工具")

        with gr.Row(equal_height=False):
            # ========== 左栏：水印库 ==========
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### 水印库")

                with gr.Tabs() as wm_tabs:
                    # --- 图片水印库 ---
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
                        with gr.Row():
                            upload_img_wm = gr.File(
                                label="上传图片水印",
                                file_types=["image"],
                                file_count="single",
                                show_label=False,
                                scale=3,
                            )
                            upload_img_btn = gr.Button("上传", size="sm", scale=1)
                        img_wm_opacity = gr.Slider(
                            minimum=0.05, maximum=1.0, value=0.7, step=0.05,
                            label="图片水印透明度"
                        )

                    # --- 文字水印库 ---
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
                        wm_text_opacity = gr.Slider(minimum=0.05, maximum=1.0, value=0.7, step=0.05, label="透明度")
                        with gr.Row():
                            wm_text_name = gr.Textbox(label="名称", placeholder="为水印命名", scale=2)
                            save_txt_wm_btn = gr.Button("保存", size="sm", scale=1)

                with gr.Row():
                    refresh_wm_btn = gr.Button("刷新水印库", size="sm")
                    delete_img_wm_btn = gr.Button("删除选中图片水印", size="sm")
                    delete_txt_wm_btn = gr.Button("删除选中文字水印", size="sm")

                wm_status = gr.Textbox(label="状态", interactive=False, lines=1, show_label=False)

            # ========== 中栏：编辑区 ==========
            with gr.Column(scale=2, min_width=400):
                gr.Markdown("### 编辑区")

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
                        minimum=10, maximum=500, value=100, step=5,
                        label="水印大小 (%)", elem_id="watermark_size"
                    )
                    wm_rotation_slider = gr.Slider(
                        minimum=0, maximum=360, value=0, step=5,
                        label="旋转角度", elem_id="watermark_rotation"
                    )

                # 当前水印列表展示
                watermark_info = gr.Textbox(
                    label="已添加的水印",
                    interactive=False,
                    lines=3,
                    placeholder="尚未添加水印，请先选择水印然后点击编辑区的图片添加",
                )

                # 隐藏组件
                fetched_image_data = gr.Textbox(visible=False, elem_id="watermark_fetched_image_data")
                click_coords = gr.Textbox(visible=False, elem_id="watermark_click_coords")

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

        def refresh_galleries():
            return manager.get_image_watermark_gallery(), manager.get_text_watermark_gallery()

        def upload_image_watermark(file):
            if file is None:
                return "请选择文件", manager.get_image_watermark_gallery()
            filename = Path(file.name).name
            save_path = manager.images_dir / filename
            shutil.copy(file.name, save_path)
            return f"已上传: {filename}", manager.get_image_watermark_gallery()

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
            # 删除旧预览
            preview_path = manager.texts_dir / f"{name}_preview.png"
            if preview_path.exists():
                preview_path.unlink()
            return f"已保存: {name}", manager.get_text_watermark_gallery()

        def select_image_watermark(evt: gr.SelectData, opacity):
            imgs = manager.list_image_watermarks()
            if evt.index < len(imgs):
                path = imgs[evt.index]
                name = Path(path).stem
                return "image", {"type": "image", "path": path, "opacity": opacity}, f"已选择图片水印: {name}"
            return "image", {}, "选择失败"

        def select_text_watermark(evt: gr.SelectData):
            texts = manager.list_text_watermarks()
            if evt.index < len(texts):
                data = texts[evt.index]
                return "text", data, f"已选择文字水印: {data.get('text', '?')}"
            return "text", {}, "选择失败"

        def add_watermark_at_position(coords_json, wm_type, wm_data, wm_list, size, rotation, img_opacity):
            """通过 JS 点击坐标添加水印"""
            if not coords_json:
                return wm_list, format_watermark_list(wm_list)
            try:
                coords = json.loads(coords_json)
            except Exception:
                return wm_list, format_watermark_list(wm_list)

            x_ratio = coords.get('x', 0.5)
            y_ratio = coords.get('y', 0.5)

            new_wm = {
                'type': wm_type,
                'x': x_ratio,
                'y': y_ratio,
                'size': size,
                'rotation': rotation,
            }

            if wm_type == 'text' and wm_data:
                new_wm['text'] = wm_data.get('text', '水印')
                new_wm['color'] = wm_data.get('color', '#FFFFFF')
                new_wm['opacity'] = wm_data.get('opacity', 0.7)
                new_wm['font_size'] = wm_data.get('font_size', 48)
            elif wm_type == 'image' and wm_data:
                new_wm['path'] = wm_data.get('path', '')
                new_wm['opacity'] = img_opacity
            else:
                return wm_list, format_watermark_list(wm_list) + "\n(请先选择一个水印)"

            wm_list = wm_list or []
            wm_list = list(wm_list) + [new_wm]
            return wm_list, format_watermark_list(wm_list)

        def format_watermark_list(wm_list):
            if not wm_list:
                return "尚未添加水印"
            lines = []
            for i, wm in enumerate(wm_list):
                if wm['type'] == 'text':
                    lines.append(f"  [{i+1}] 文字: \"{wm.get('text', '')}\" 位置:({wm['x']:.2f}, {wm['y']:.2f}) 大小:{wm['size']}% 角度:{wm['rotation']}°")
                else:
                    name = Path(wm.get('path', '')).stem if wm.get('path') else '?'
                    lines.append(f"  [{i+1}] 图片: {name} 位置:({wm['x']:.2f}, {wm['y']:.2f}) 大小:{wm['size']}% 角度:{wm['rotation']}° 透明度:{wm.get('opacity', 1.0):.0%}")
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
            output_dir = Path("outputs/watermarked")
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = output_dir / f"watermarked_{ts}.png"
            img.save(path)
            return f"已保存: {path}"

        def save_extractable(img):
            if img is None or manager.original_image is None:
                return "没有可保存的图片，请先生成"
            output_dir = Path("outputs/watermarked")
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = output_dir / f"extractable_{ts}.png"
            manager.create_extractable_image(img, manager.original_image, path)
            return f"可解压图片包已保存: {path}\n将 .png 改为 .zip 即可解压出原图"

        def fetch_last_image(image_data_url):
            if not image_data_url or not image_data_url.startswith("data:"):
                return gr.update()
            header, encoded = image_data_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            img = Image.open(io.BytesIO(image_bytes))
            return img

        def delete_selected_img_wm(evt: gr.SelectData):
            imgs = manager.list_image_watermarks()
            if evt.index < len(imgs):
                path = Path(imgs[evt.index])
                if path.exists():
                    path.unlink()
                return f"已删除: {path.name}", manager.get_image_watermark_gallery()
            return "未选中", manager.get_image_watermark_gallery()

        def delete_selected_txt_wm(evt: gr.SelectData):
            texts = manager.list_text_watermarks()
            if evt.index < len(texts):
                data = texts[evt.index]
                json_path = Path(data['_path'])
                preview_path = manager.texts_dir / f"{data['_filename']}_preview.png"
                if json_path.exists():
                    json_path.unlink()
                if preview_path.exists():
                    preview_path.unlink()
                return f"已删除: {data['_filename']}", manager.get_text_watermark_gallery()
            return "未选中", manager.get_text_watermark_gallery()

        # 删除使用State记录选中索引
        selected_img_idx = gr.State(-1)
        selected_txt_idx = gr.State(-1)

        # --- 绑定事件 ---

        # 刷新水印库
        refresh_wm_btn.click(fn=refresh_galleries, outputs=[img_wm_gallery, txt_wm_gallery])

        # 上传图片水印
        upload_img_btn.click(
            fn=upload_image_watermark,
            inputs=[upload_img_wm],
            outputs=[wm_status, img_wm_gallery]
        )

        # 保存文字水印
        save_txt_wm_btn.click(
            fn=save_text_watermark,
            inputs=[wm_text_input, wm_font_size, wm_text_color, wm_text_opacity, wm_text_name],
            outputs=[wm_status, txt_wm_gallery]
        )

        # 选择水印
        img_wm_gallery.select(
            fn=select_image_watermark,
            inputs=[img_wm_opacity],
            outputs=[selected_wm_type, selected_wm_data, wm_status]
        )
        txt_wm_gallery.select(
            fn=select_text_watermark,
            outputs=[selected_wm_type, selected_wm_data, wm_status]
        )

        # 记录选中索引用于删除
        def record_img_idx(evt: gr.SelectData):
            return evt.index

        def record_txt_idx(evt: gr.SelectData):
            return evt.index

        img_wm_gallery.select(fn=record_img_idx, outputs=[selected_img_idx])
        txt_wm_gallery.select(fn=record_txt_idx, outputs=[selected_txt_idx])

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

        # 点击坐标 -> 添加水印
        click_coords.change(
            fn=add_watermark_at_position,
            inputs=[click_coords, selected_wm_type, selected_wm_data, watermark_list_state, wm_size_slider, wm_rotation_slider, img_wm_opacity],
            outputs=[watermark_list_state, watermark_info]
        )

        # 撤销 / 清除水印
        undo_btn.click(fn=undo_watermark, inputs=[watermark_list_state], outputs=[watermark_list_state, watermark_info])
        clear_wm_btn.click(fn=clear_watermarks, outputs=[watermark_list_state, watermark_info])
        clear_btn.click(fn=clear_image, outputs=[image_editor, preview_image, watermark_list_state, watermark_info])

        # 获取上次生成的图片
        fetch_last_btn.click(
            fn=None,
            inputs=[],
            outputs=[fetched_image_data],
            _js="() => window.watermarkFetchLastImage()"
        )
        fetched_image_data.change(fn=fetch_last_image, inputs=[fetched_image_data], outputs=[image_editor])

        # 生成
        generate_btn.click(
            fn=generate_watermarked,
            inputs=[image_editor, watermark_list_state],
            outputs=[preview_image, save_status]
        )

        # 保存
        save_btn.click(fn=save_normal, inputs=[preview_image], outputs=[save_status])
        save_extract_btn.click(fn=save_extractable, inputs=[preview_image], outputs=[save_status])

        # 页面加载时刷新水印库
        watermark_tab.load(fn=refresh_galleries, outputs=[img_wm_gallery, txt_wm_gallery])

    return [(watermark_tab, "Watermark Adder", "watermark_adder_tab")]


script_callbacks.on_ui_tabs(on_ui_tabs)
