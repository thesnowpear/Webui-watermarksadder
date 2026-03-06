// 水印画布交互脚本
// 通过 #watermark_selected_bridge 与 Python 端同步选中状态
// 通过 #watermark_click_coords 将点击坐标发回 Python
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
        selectedType: null,
        selectedData: {},
        // 前端已添加水印的预览列表 (仅用于 canvas 绘制)
        watermarks: [],
        size: 100,
        rotation: 0,
        opacity: 0.7,
        canvasReady: false,
        // 图片水印缓存: path -> Image
        imgCache: {},
    };

    // ============ 初始化 ============
    function init() {
        console.log('[Watermark] Initializing...');

        const poll = setInterval(() => {
            const editorWrap = document.querySelector('#watermark_editor');
            if (!editorWrap) return;

            clearInterval(poll);
            state.editorEl = editorWrap;

            watchBridge();
            watchSliders();
            watchForImage();

            console.log('[Watermark] Watcher started');
        }, 500);
    }

    // ============ Bridge: 监听 Python->JS 的选中信息 ============
    function watchBridge() {
        const poll = setInterval(() => {
            const bridgeEl = document.querySelector('#watermark_selected_bridge textarea');
            if (!bridgeEl) return;

            clearInterval(poll);

            const observer = new MutationObserver(() => readBridge(bridgeEl));
            observer.observe(bridgeEl, { attributes: true, childList: true, characterData: true });
            bridgeEl.addEventListener('input', () => readBridge(bridgeEl));
            // 轮询兜底
            setInterval(() => readBridge(bridgeEl), 500);

            console.log('[Watermark] Bridge connected');
        }, 300);
    }

    let lastBridgeValue = '';

    function readBridge(el) {
        const val = el.value || '';
        if (val === lastBridgeValue || !val) return;
        lastBridgeValue = val;

        try {
            const data = JSON.parse(val);
            if (!data.type) {
                // 取消选择
                state.selectedType = null;
                state.selectedData = {};
                console.log('[Watermark] Deselected');
            } else {
                state.selectedType = data.type;
                state.selectedData = data;
                // 预加载图片水印
                if (data.type === 'image' && data.path) {
                    preloadWatermarkImage(data.path);
                }
                console.log('[Watermark] Selected:', data.type);
            }
            redraw();
        } catch (e) {
            // ignore
        }
    }

    // 预加载水印图片到缓存
    function preloadWatermarkImage(path) {
        if (state.imgCache[path]) return;
        const img = new window.Image();
        img.onload = () => {
            state.imgCache[path] = img;
            console.log('[Watermark] Image cached:', path, img.width, 'x', img.height);
            redraw();
        };
        img.onerror = () => {
            console.warn('[Watermark] Failed to load image:', path);
        };
        // WebUI 通过 /file= 路由访问扩展文件
        img.src = '/file=' + path;
    }

    // ============ 监听图片出现/消失并管理 Canvas ============
    function watchForImage() {
        const editorWrap = state.editorEl;

        function trySetupCanvas() {
            const imgEl = editorWrap.querySelector('img');

            // 图片不存在或被清除 -> 移除 canvas
            if (!imgEl || !imgEl.src || imgEl.src === '' || imgEl.src === 'data:,') {
                if (state.canvasReady) {
                    removeCanvas();
                }
                return;
            }

            // 同一个 img 元素且 canvas 已就绪 -> 只同步尺寸
            if (state.canvasReady && state.imgEl === imgEl) {
                syncCanvasSize();
                return;
            }

            // 新的 img 元素出现 -> 创建 canvas
            state.imgEl = imgEl;
            removeCanvas();

            // 等图片完全加载（包括解码）再创建 canvas
            if (imgEl.complete && imgEl.naturalWidth > 0) {
                // 使用 decode() 确保图片完全解码，避免半黑问题
                if (imgEl.decode) {
                    imgEl.decode().then(() => {
                        requestAnimationFrame(() => setupCanvas());
                    }).catch(() => {
                        requestAnimationFrame(() => setupCanvas());
                    });
                } else {
                    requestAnimationFrame(() => setupCanvas());
                }
            } else {
                imgEl.addEventListener('load', () => {
                    // load 后再等一帧确保渲染完成
                    setTimeout(() => {
                        requestAnimationFrame(() => setupCanvas());
                    }, 100);
                }, { once: true });
            }
        }

        const observer = new MutationObserver(() => {
            // 延迟一帧避免频繁触发
            requestAnimationFrame(trySetupCanvas);
        });
        observer.observe(editorWrap, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });

        setInterval(trySetupCanvas, 1500);
        trySetupCanvas();
    }

    // ============ Canvas 创建/移除 ============
    function setupCanvas() {
        const imgEl = state.imgEl;
        if (!imgEl) return;

        const container = imgEl.closest('.image-container')
            || imgEl.closest('[data-testid="image"]')
            || imgEl.parentElement;
        if (!container) return;

        // 移除旧的
        removeCanvas();

        const canvas = document.createElement('canvas');
        canvas.id = 'watermark-overlay-canvas';

        const containerRect = container.getBoundingClientRect();
        const imgRect = imgEl.getBoundingClientRect();

        const offsetTop = imgRect.top - containerRect.top;
        const offsetLeft = imgRect.left - containerRect.left;

        canvas.style.cssText =
            'position:absolute;' +
            'top:' + offsetTop + 'px;' +
            'left:' + offsetLeft + 'px;' +
            'width:' + imgRect.width + 'px;' +
            'height:' + imgRect.height + 'px;' +
            'z-index:100;pointer-events:auto;cursor:crosshair;';

        canvas.width = Math.round(imgRect.width);
        canvas.height = Math.round(imgRect.height);

        const containerStyle = window.getComputedStyle(container);
        if (containerStyle.position === 'static') {
            container.style.position = 'relative';
        }

        container.appendChild(canvas);

        state.canvas = canvas;
        state.ctx = canvas.getContext('2d');
        state.canvasReady = true;

        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('mouseleave', onMouseLeave);
        canvas.addEventListener('mouseenter', () => { state.isHovering = true; });
        canvas.addEventListener('click', onClick);
        canvas.addEventListener('wheel', onWheel, { passive: false });

        if (state._resizeObserver) {
            state._resizeObserver.disconnect();
        }
        state._resizeObserver = new ResizeObserver(() => syncCanvasSize());
        state._resizeObserver.observe(imgEl);

        console.log('[Watermark] Canvas ready', canvas.width, 'x', canvas.height);
        redraw();
    }

    function removeCanvas() {
        const old = document.querySelector('#watermark-overlay-canvas');
        if (old) old.remove();
        if (state._resizeObserver) {
            state._resizeObserver.disconnect();
            state._resizeObserver = null;
        }
        state.canvas = null;
        state.ctx = null;
        state.canvasReady = false;
    }

    function syncCanvasSize() {
        if (!state.canvas || !state.imgEl) return;

        const container = state.canvas.parentElement;
        if (!container) return;

        const containerRect = container.getBoundingClientRect();
        const imgRect = state.imgEl.getBoundingClientRect();

        if (imgRect.width === 0 || imgRect.height === 0) return;

        const offsetTop = imgRect.top - containerRect.top;
        const offsetLeft = imgRect.left - containerRect.left;
        const w = Math.round(imgRect.width);
        const h = Math.round(imgRect.height);

        // 只在尺寸变化时更新
        if (state.canvas.width === w && state.canvas.height === h) return;

        state.canvas.style.top = offsetTop + 'px';
        state.canvas.style.left = offsetLeft + 'px';
        state.canvas.style.width = w + 'px';
        state.canvas.style.height = h + 'px';
        state.canvas.width = w;
        state.canvas.height = h;

        redraw();
    }

    // ============ 滑块监听 ============
    function watchSliders() {
        const poll = setInterval(() => {
            const sizeEl = document.querySelector('#watermark_size input[type="range"]')
                || document.querySelector('#watermark_size input[type="number"]');
            const rotEl = document.querySelector('#watermark_rotation input[type="range"]')
                || document.querySelector('#watermark_rotation input[type="number"]');
            const opacEl = document.querySelector('#watermark_opacity input[type="range"]')
                || document.querySelector('#watermark_opacity input[type="number"]');

            if (sizeEl && rotEl && opacEl) {
                clearInterval(poll);
                sizeEl.addEventListener('input', (e) => { state.size = parseFloat(e.target.value); redraw(); });
                rotEl.addEventListener('input', (e) => { state.rotation = parseFloat(e.target.value); redraw(); });
                opacEl.addEventListener('input', (e) => { state.opacity = parseFloat(e.target.value); redraw(); });
                state.size = parseFloat(sizeEl.value) || 100;
                state.rotation = parseFloat(rotEl.value) || 0;
                state.opacity = parseFloat(opacEl.value) || 0.7;
                console.log('[Watermark] Sliders connected');
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
        const xRatio = cx / rect.width;
        const yRatio = cy / rect.height;

        // 添加到前端预览列表
        state.watermarks.push({
            type: state.selectedType,
            data: { ...state.selectedData },
            x: cx,
            y: cy,
            xRatio: xRatio,
            yRatio: yRatio,
            size: state.size,
            rotation: state.rotation,
            opacity: state.opacity,
        });

        redraw();

        // 发送坐标到 Python
        const coordsEl = document.querySelector('#watermark_click_coords textarea');
        if (coordsEl) {
            const value = JSON.stringify({ x: xRatio, y: yRatio, ts: Date.now() });
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            nativeSetter.call(coordsEl, value);
            coordsEl.dispatchEvent(new Event('input', { bubbles: true }));
        }

        console.log('[Watermark] Click at', xRatio.toFixed(3), yRatio.toFixed(3));
    }

    function onWheel(e) {
        e.preventDefault();
        if (e.ctrlKey) {
            // Ctrl+滚轮：调整大小
            const delta = e.deltaY > 0 ? -3 : 3;
            state.size = Math.max(1, Math.min(1000, state.size + delta));
            updateSlider('#watermark_size', state.size);
        } else if (e.shiftKey) {
            // Shift+滚轮：调整角度
            const delta = e.deltaY > 0 ? -5 : 5;
            state.rotation = (state.rotation + delta + 360) % 360;
            updateSlider('#watermark_rotation', state.rotation);
        } else if (e.altKey) {
            // Alt+滚轮：调整透明度
            const delta = e.deltaY > 0 ? -0.05 : 0.05;
            state.opacity = Math.max(0.05, Math.min(1.0, +(state.opacity + delta).toFixed(2)));
            updateSlider('#watermark_opacity', state.opacity);
        }
        redraw();
    }

    function updateSlider(selector, value) {
        const rangeEl = document.querySelector(selector + ' input[type="range"]');
        const numEl = document.querySelector(selector + ' input[type="number"]');
        [rangeEl, numEl].forEach(el => {
            if (el) {
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(el, value);
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    }

    // ============ 绘制 ============
    function redraw() {
        const ctx = state.ctx;
        const canvas = state.canvas;
        if (!ctx || !canvas) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 已添加的水印
        state.watermarks.forEach((wm) => {
            drawWatermarkPreview(ctx, wm, wm.opacity || 0.7);
        });

        // 鼠标跟随预览 - 使用真实透明度，加虚线边框区分
        if (state.isHovering && state.selectedType) {
            drawWatermarkPreview(ctx, {
                type: state.selectedType,
                data: state.selectedData,
                x: state.mouseX,
                y: state.mouseY,
                size: state.size,
                rotation: state.rotation,
                opacity: state.opacity,
                isPreview: true,
            }, state.opacity);
        }
    }

    function drawWatermarkPreview(ctx, wm, alpha) {
        ctx.save();
        ctx.globalAlpha = Math.max(0.05, alpha);
        ctx.translate(wm.x, wm.y);
        ctx.rotate((wm.rotation * Math.PI) / 180);

        if (wm.type === 'text') {
            const baseFontSize = wm.data.font_size || wm.data.fontSize || 48;
            // 与 Python 一致: scaled = font_size * size / 100, 然后用 displayRatio 映射到 canvas
            let displayRatio = 1;
            if (state.imgEl && state.imgEl.naturalWidth > 0 && state.canvas) {
                displayRatio = state.canvas.width / state.imgEl.naturalWidth;
            }
            const fontSize = Math.max(4, baseFontSize * wm.size / 100 * displayRatio);
            ctx.font = 'bold ' + fontSize + 'px Arial, sans-serif';
            ctx.fillStyle = wm.data.color || '#FFFFFF';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.strokeStyle = 'rgba(0,0,0,0.5)';
            ctx.lineWidth = Math.max(1, fontSize / 20);
            const text = wm.data.text || '水印';
            ctx.strokeText(text, 0, 0);
            ctx.fillText(text, 0, 0);

            // 鼠标跟随预览加虚线边框
            if (wm.isPreview) {
                const m = ctx.measureText(text);
                const bw = m.width + 8;
                const bh = fontSize + 8;
                ctx.globalAlpha = 0.6;
                ctx.strokeStyle = '#00aaff';
                ctx.lineWidth = 1;
                ctx.setLineDash([4, 3]);
                ctx.strokeRect(-bw / 2, -bh / 2, bw, bh);
                ctx.setLineDash([]);
            }

        } else if (wm.type === 'image') {
            // 图片水印预览：使用真实图片
            const path = wm.data.path || '';
            const cachedImg = state.imgCache[path];

            if (cachedImg) {
                // 用真实图片绘制，尺寸比例与 Python 一致
                // Python: scale = size / 100, new_w = img.width * scale
                // Canvas 上需要按显示比例缩放：canvas.width / 原图宽度
                const scale = wm.size / 100;
                // 估算原图与 canvas 的比例 (使用 imgEl 的自然尺寸)
                let displayRatio = 1;
                if (state.imgEl && state.imgEl.naturalWidth > 0 && state.canvas) {
                    displayRatio = state.canvas.width / state.imgEl.naturalWidth;
                }
                const drawW = cachedImg.width * scale * displayRatio;
                const drawH = cachedImg.height * scale * displayRatio;
                ctx.drawImage(cachedImg, -drawW / 2, -drawH / 2, drawW, drawH);

                // 鼠标跟随预览加虚线边框
                if (wm.isPreview) {
                    ctx.globalAlpha = 0.6;
                    ctx.strokeStyle = '#00aaff';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([4, 3]);
                    ctx.strokeRect(-drawW / 2 - 2, -drawH / 2 - 2, drawW + 4, drawH + 4);
                    ctx.setLineDash([]);
                }
            } else {
                // 图片未加载 -> 尝试加载并显示占位
                if (path && !state.imgCache['_loading_' + path]) {
                    state.imgCache['_loading_' + path] = true;
                    preloadWatermarkImage(path);
                }
                const s = Math.max(20, wm.size * 0.5);
                ctx.strokeStyle = 'rgba(0,255,136,0.8)';
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 4]);
                ctx.strokeRect(-s / 2, -s / 2, s, s);
                ctx.setLineDash([]);
                ctx.fillStyle = 'rgba(0,255,136,0.8)';
                ctx.font = '11px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('loading...', 0, 0);
            }
        }

        ctx.restore();
    }

    // ============ 全局接口 (被 Python _js 调用) ============

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

    window.watermarkRemoveCanvas = function () {
        state.watermarks = [];
        removeCanvas();
        state.imgEl = null;
    };

    // ============ 启动 ============
    if (typeof onUiLoaded === 'function') {
        onUiLoaded(init);
    } else if (typeof onUiUpdate === 'function') {
        let started = false;
        onUiUpdate(() => {
            if (!started) {
                started = true;
                init();
            }
        });
    } else {
        document.addEventListener('DOMContentLoaded', () => setTimeout(init, 1500));
        if (document.readyState !== 'loading') {
            setTimeout(init, 1500);
        }
    }

    console.log('[Watermark] Script loaded');
})();
