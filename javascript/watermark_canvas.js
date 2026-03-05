// 水印画布交互脚本
(function () {
    'use strict';

    let state = {
        canvas: null,
        ctx: null,
        editorEl: null,
        imgEl: null,
        isHovering: false,
        mouseX: 0,
        mouseY: 0,
        selectedType: null, // 'text' | 'image'
        selectedData: {},
        watermarks: [],
        size: 100,
        rotation: 0,
        initialized: false,
    };

    // ============ 初始化 ============
    function init() {
        if (state.initialized) return;
        console.log('[Watermark] Initializing...');

        const poll = setInterval(() => {
            const editorWrap = document.querySelector('#watermark_editor');
            if (!editorWrap) return;

            // Gradio Image 组件内的 img 元素
            const imgEl = editorWrap.querySelector('img');
            if (!imgEl) return;

            clearInterval(poll);
            state.editorEl = editorWrap;
            state.imgEl = imgEl;
            state.initialized = true;

            setupCanvas();
            setupSliderListeners();
            observeImageChanges();

            console.log('[Watermark] Ready');
        }, 800);
    }

    // ============ Canvas 覆盖层 ============
    function setupCanvas() {
        // 找到包含图片的容器
        const container = state.imgEl.closest('.image-container') || state.imgEl.parentElement;
        if (!container) return;

        const canvas = document.createElement('canvas');
        canvas.id = 'watermark-overlay-canvas';
        canvas.style.cssText = 'position:absolute;top:0;left:0;z-index:100;pointer-events:auto;cursor:crosshair;';

        container.style.position = 'relative';
        container.appendChild(canvas);

        state.canvas = canvas;
        state.ctx = canvas.getContext('2d');

        syncCanvasSize();

        // 事件
        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('mouseleave', onMouseLeave);
        canvas.addEventListener('mouseenter', () => { state.isHovering = true; });
        canvas.addEventListener('click', onClick);
        canvas.addEventListener('wheel', onWheel, { passive: false });

        // 窗口大小变化时更新
        new ResizeObserver(() => syncCanvasSize()).observe(container);
    }

    function syncCanvasSize() {
        if (!state.canvas || !state.imgEl) return;
        const rect = state.imgEl.getBoundingClientRect();
        state.canvas.width = rect.width;
        state.canvas.height = rect.height;
        state.canvas.style.width = rect.width + 'px';
        state.canvas.style.height = rect.height + 'px';
        redraw();
    }

    // ============ 监听图片变化 ============
    function observeImageChanges() {
        // Gradio 切换图片时可能替换 img 元素
        const editorWrap = state.editorEl;
        const observer = new MutationObserver(() => {
            const newImg = editorWrap.querySelector('img');
            if (newImg && newImg !== state.imgEl) {
                state.imgEl = newImg;
                // 重建 canvas（容器可能变了）
                if (state.canvas && state.canvas.parentElement) {
                    state.canvas.remove();
                }
                state.initialized = false;
                setTimeout(() => {
                    state.initialized = true;
                    setupCanvas();
                }, 300);
            } else if (newImg) {
                setTimeout(syncCanvasSize, 100);
            }
        });
        observer.observe(editorWrap, { childList: true, subtree: true, attributes: true });
    }

    // ============ 滑块监听 ============
    function setupSliderListeners() {
        const pollSliders = setInterval(() => {
            const sizeEl = document.querySelector('#watermark_size input[type="range"], #watermark_size input[type="number"]');
            const rotEl = document.querySelector('#watermark_rotation input[type="range"], #watermark_rotation input[type="number"]');
            if (sizeEl && rotEl) {
                clearInterval(pollSliders);
                sizeEl.addEventListener('input', (e) => { state.size = parseFloat(e.target.value); redraw(); });
                rotEl.addEventListener('input', (e) => { state.rotation = parseFloat(e.target.value); redraw(); });
                state.size = parseFloat(sizeEl.value) || 100;
                state.rotation = parseFloat(rotEl.value) || 0;
            }
        }, 500);
    }

    // ============ 鼠标事件 ============
    function onMouseMove(e) {
        state.isHovering = true;
        const rect = state.canvas.getBoundingClientRect();
        state.mouseX = e.clientX - rect.left;
        state.mouseY = e.clientY - rect.top;
        redraw();
    }

    function onMouseLeave() {
        state.isHovering = false;
        redraw();
    }

    function onClick(e) {
        if (!state.selectedType) {
            console.log('[Watermark] No watermark selected');
            return;
        }

        const rect = state.canvas.getBoundingClientRect();
        const cx = e.clientX - rect.left;
        const cy = e.clientY - rect.top;

        // 转为相对比例 (0~1)
        const xRatio = cx / rect.width;
        const yRatio = cy / rect.height;

        // 添加到本地预览列表
        state.watermarks.push({
            type: state.selectedType,
            data: { ...state.selectedData },
            x: cx,
            y: cy,
            xRatio: xRatio,
            yRatio: yRatio,
            size: state.size,
            rotation: state.rotation,
        });

        redraw();

        // 传递坐标到 Gradio hidden input
        const coordsEl = document.querySelector('#watermark_click_coords textarea');
        if (coordsEl) {
            const value = JSON.stringify({ x: xRatio, y: yRatio, ts: Date.now() });
            coordsEl.value = value;
            coordsEl.dispatchEvent(new Event('input', { bubbles: true }));
        }

        console.log('[Watermark] Added at', xRatio.toFixed(2), yRatio.toFixed(2));
    }

    function onWheel(e) {
        e.preventDefault();
        if (e.ctrlKey) {
            const delta = e.deltaY > 0 ? -5 : 5;
            state.rotation = (state.rotation + delta + 360) % 360;
            updateSlider('#watermark_rotation', state.rotation);
        } else {
            const delta = e.deltaY > 0 ? -10 : 10;
            state.size = Math.max(10, Math.min(500, state.size + delta));
            updateSlider('#watermark_size', state.size);
        }
        redraw();
    }

    function updateSlider(selector, value) {
        const el = document.querySelector(selector + ' input[type="range"]');
        if (el) {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
        const numEl = document.querySelector(selector + ' input[type="number"]');
        if (numEl) {
            numEl.value = value;
            numEl.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    // ============ 绘制 ============
    function redraw() {
        const ctx = state.ctx;
        const canvas = state.canvas;
        if (!ctx || !canvas) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 已添加的水印
        state.watermarks.forEach((wm) => {
            drawWatermarkPreview(ctx, wm, 0.8);
        });

        // 鼠标跟随预览
        if (state.isHovering && state.selectedType) {
            drawWatermarkPreview(ctx, {
                type: state.selectedType,
                data: state.selectedData,
                x: state.mouseX,
                y: state.mouseY,
                size: state.size,
                rotation: state.rotation,
            }, 0.4);
        }
    }

    function drawWatermarkPreview(ctx, wm, alpha) {
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.translate(wm.x, wm.y);
        ctx.rotate((wm.rotation * Math.PI) / 180);

        if (wm.type === 'text') {
            const fontSize = Math.max(8, (wm.data.font_size || 48) * wm.size / 100 * 0.5);
            ctx.font = `${fontSize}px Arial, sans-serif`;
            ctx.fillStyle = wm.data.color || '#FFFFFF';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.strokeStyle = 'rgba(0,0,0,0.5)';
            ctx.lineWidth = 1;
            const text = wm.data.text || '水印';
            ctx.strokeText(text, 0, 0);
            ctx.fillText(text, 0, 0);
        } else if (wm.type === 'image') {
            // 用占位矩形表示图片水印
            const s = wm.size * 0.5;
            ctx.strokeStyle = '#00ff88';
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 4]);
            ctx.strokeRect(-s / 2, -s / 2, s, s);
            ctx.setLineDash([]);

            // 加载并绘制实际图片
            if (wm.data.path && !wm._imgLoaded) {
                // 尝试加载 (仅在 file:// 或同源时有效, webui 通常使用 /file= 路由)
                const img = new window.Image();
                img.onload = () => {
                    wm._img = img;
                    wm._imgLoaded = true;
                    redraw();
                };
                // webui 通常可以通过 /file= 路径访问扩展文件
                img.src = '/file=' + wm.data.path;
                wm._imgLoaded = true; // 标记已尝试
            }
            if (wm._img) {
                const scale = wm.size / 100;
                const w = wm._img.width * scale * 0.3;
                const h = wm._img.height * scale * 0.3;
                ctx.drawImage(wm._img, -w / 2, -h / 2, w, h);
            }
        }

        ctx.restore();
    }

    // ============ 全局接口 ============

    // 由 Python/Gradio 端调用来设置选中水印
    window.watermarkSetSelected = function (type, data) {
        state.selectedType = type;
        state.selectedData = data || {};
        console.log('[Watermark] Selected:', type, data);
    };

    // Gallery 选中时自动设置 (通过 Gradio 事件回调中的 _js 调用)
    window.watermarkSelectImageWatermark = function (path, opacity) {
        state.selectedType = 'image';
        state.selectedData = { type: 'image', path: path, opacity: opacity || 0.7 };
    };

    window.watermarkSelectTextWatermark = function (data) {
        state.selectedType = 'text';
        state.selectedData = data || {};
    };

    window.watermarkUndo = function () {
        if (state.watermarks.length > 0) {
            state.watermarks.pop();
            redraw();
        }
    };

    window.watermarkClearAll = function () {
        state.watermarks = [];
        redraw();
    };

    // 获取上次生成的图片
    window.watermarkFetchLastImage = function () {
        const selectors = [
            '#txt2img_gallery img[data-testid="detailed-image"]',
            '#img2img_gallery img[data-testid="detailed-image"]',
            '#txt2img_gallery .gallery-item img',
            '#img2img_gallery .gallery-item img',
            '#txt2img_gallery .thumbnails img',
            '#img2img_gallery .thumbnails img',
            '#txt2img_gallery .grid-wrap img',
            '#img2img_gallery .grid-wrap img',
            '#txt2img_gallery .preview img',
            '#img2img_gallery .preview img',
            '#txt2img_gallery img',
            '#img2img_gallery img',
        ];

        let imgSrc = null;
        for (const sel of selectors) {
            const imgs = document.querySelectorAll(sel);
            if (imgs.length > 0) {
                imgSrc = imgs[0].src;
                break;
            }
        }

        if (!imgSrc) {
            alert('未找到生成的图片。请先在 txt2img 或 img2img 中生成图片。');
            return null;
        }

        if (imgSrc.startsWith('data:')) {
            return imgSrc;
        }

        // 通过 canvas 转换为 data URL
        return new Promise((resolve) => {
            const tmp = new window.Image();
            tmp.crossOrigin = 'anonymous';
            tmp.onload = function () {
                const c = document.createElement('canvas');
                c.width = tmp.naturalWidth;
                c.height = tmp.naturalHeight;
                c.getContext('2d').drawImage(tmp, 0, 0);
                resolve(c.toDataURL('image/png'));
            };
            tmp.onerror = function () {
                alert('获取图片失败，可能存在跨域限制。');
                resolve(null);
            };
            tmp.src = imgSrc;
        });
    };

    // ============ 启动 ============
    // Gradio / webui 使用 onUiLoaded 或 DOMContentLoaded
    if (typeof onUiLoaded === 'function') {
        onUiLoaded(init);
    } else if (typeof onUiUpdate === 'function') {
        onUiUpdate(init);
    } else {
        document.addEventListener('DOMContentLoaded', () => setTimeout(init, 1000));
        // 兜底: 如果 DOMContentLoaded 已触发
        if (document.readyState !== 'loading') {
            setTimeout(init, 1000);
        }
    }

    console.log('[Watermark] Script loaded');
})();
