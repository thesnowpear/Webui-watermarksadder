# WebUI-Forge 水印添加扩展

[English](README.md) | 简体中文

这是一个用于 Stable Diffusion WebUI Forge 的扩展程序，提供强大的图片水印添加功能。

## 功能特性

### 核心功能
- **文字水印**：创建和保存自定义文字水印，支持颜色、字号、透明度调整
- **图片水印**：上传和管理图片水印（支持 PNG 透明背景），上传后自动保存到水印库
- **可视化编辑**：Canvas 覆盖层实时预览，鼠标跟随水印，点击放置
- **撤销/清除**：支持撤销最后添加的水印或清除所有水印

### 图像编辑区交互
- **滚轮**：缩放图片视图
- **长按左键拖拽**：平移图片视图
- **双击**：重置缩放和平移
- **Ctrl + 滚轮**：调整水印大小（±20px）
- **Shift + 滚轮**：调整水印旋转角度
- **Alt + 滚轮**：调整水印透明度
- **单击**：在鼠标位置放置水印

### 水印大小
- 以像素为单位（最短边），范围 1–2000px
- 文字水印：size 即字号像素
- 图片水印：size 为最短边像素数，等比缩放

### 保存选项
- **保存图片**：保存为标准 PNG 格式的带水印图片
- **保存可解压包**：特殊的 Polyglot 文件
  - 外观是普通 PNG 图片（显示带水印版本）
  - 将后缀改为 `.zip` 可以解压出原始无水印图片
  - 一个文件包含两个版本

### 其他功能
- **自动保存**：生成水印图片时默认自动保存到 `outputs/watermarked/`
- **获取上次生成的图片**：自动扫描 `outputs/` 文件夹，按修改时间获取最新图片（排除 `outputs/watermarked/` 水印输出目录）
- **取消选择**：一键取消当前选中的水印
- **水印库管理**：刷新、删除图片/文字水印

## 安装方法

### 方法 1：Git 克隆（推荐）

```bash
cd stable-diffusion-webui-forge/extensions/
git clone https://github.com/yourusername/sd-webui-watermark-adder.git
```

重启 WebUI Forge 即可。

### 方法 2：手动安装

1. 下载本项目的 ZIP 文件
2. 解压到 `stable-diffusion-webui-forge/extensions/` 目录
3. 重启 WebUI Forge

### 验证安装

启动 WebUI Forge 后，应该能在顶部标签栏看到 **Watermark Adder** 标签页（与 txt2img、img2img 同级）。

## 快速开始

### 1. 上传图片
- 在编辑区上传图片
- 或点击"获取上次生成的图片"从 `outputs/` 文件夹加载最新图片（排除水印输出目录）

### 2. 创建水印

**文字水印：**
1. 在左侧切换到"文字水印"标签页
2. 输入文字（如 "© 2024"）
3. 调整字体大小、颜色
4. 输入名称并保存

**图片水印：**
1. 在左侧切换到"图片水印"标签页
2. 拖放或点击上传 PNG 图片（建议透明背景）
3. 自动保存到水印库

### 3. 添加水印
1. 在水印库中点击选择一个水印
2. 鼠标移动到编辑区，水印跟随鼠标预览
3. 用快捷键调整大小/角度/透明度
4. 单击左键放置水印
5. 可以重复添加多个水印

### 4. 生成和保存
1. 点击"生成水印图片"（默认自动保存到 `outputs/watermarked/`）
2. 在右侧预览效果
3. 选择保存方式：
   - **保存图片**：普通 PNG
   - **保存可解压包**：将文件后缀 `.png` 改为 `.zip` 即可解压出无水印原图

## 项目结构

```
sd-webui-watermark-adder/
├── scripts/
│   └── watermark_adder.py      # 主扩展脚本（Python 后端 + Gradio UI）
├── javascript/
│   └── watermark_canvas.js     # 前端 Canvas 交互脚本
├── watermarks/
│   ├── images/                 # 图片水印存储
│   └── texts/                  # 文字水印配置（JSON）
├── install.py                  # 依赖安装（Pillow）
├── README.md                   # English
├── README_CN.md                # 中文说明
├── QUICKSTART.md               # 快速开始
└── DEVELOPMENT.md              # 开发文档
```

## 常见问题

### Q: 看不到 Watermark Adder 标签页？
确认项目在 `extensions` 目录下，已重启 WebUI Forge，查看控制台是否有报错。

### Q: 保存的文件在哪里？
默认保存在 WebUI 根目录下的 `outputs/watermarked/`。

### Q: 如何使用可解压图片包？
将保存的 `.png` 文件后缀改为 `.zip`，用解压软件打开即可看到 `original_image.png`。

### Q: 大图加载很慢或显示黑屏？
扩展使用了渐进式重试机制等待图片完全加载解码，最多等待约 9 秒。如果仍有问题，请尝试缩小图片尺寸后上传。

## 技术栈

- **后端**: Python 3.x + Gradio (`script_callbacks.on_ui_tabs()`)
- **图像处理**: Pillow (PIL)，带字体缓存和水印图片缓存
- **前端交互**: JavaScript + HTML5 Canvas + CSS Transform（缩放/平移）
- **Python↔JS 通信**: 隐藏 Textbox Bridge 模式
- **特殊格式**: Polyglot 文件（PNG + ZIP）

## 许可证

MIT License
