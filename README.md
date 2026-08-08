# 浏览器端 OCR 网页

使用 Vue 3、PaddleOCR.js 和 ONNX Runtime Web，在浏览器本地识别图片文字。

网页会使用 OCR 返回的干员名字坐标裁剪其上方技能图标，并与本地技能库进行 dHash 与颜色相似度匹配。识别结果支持候选技能手动更正和裁剪区域校准。

## 本地运行

```bash
npm install
npm run assets:setup
npm run data:sync
npm run dev
```

首次执行 `assets:setup` 会下载 PP-OCRv5 mobile 中文检测、识别模型，以及与 PaddleOCR Worker 匹配的 ONNX Runtime 资源到 `public/`。

`data:sync` 会从 [ArknightsGameResource](https://github.com/yuanyan3060/ArknightsGameResource) 生成本地干员技能索引与图标（`public/data/`、`public/skills/`），详情见 `doc/干员技能数据获取计划.md`。游戏资源版权归鹰角网络，仅供学习交流。

生产构建：

```bash
npm run build
npm run preview
```

## 当前线上地址

```text
http://175.27.249.38/
```

服务器上旧站文件保留在 `/opt/my-site`，当前 Nginx 首页指向 OCR（`/opt/ocr/current`）。

## 部署要求

将 `dist/` 作为静态网站部署。

为了启用 WebGPU 和多线程 WASM，生产服务器应为所有页面和静态资源返回：

```text
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

同时应使用 HTTPS；`localhost` 本地开发不受此限制。未满足 WebGPU 条件时，OCR 会尝试回退到 WASM。

Nginx 示例：

```nginx
location / {
    root /var/www/ocr/dist;
    try_files $uri $uri/ /index.html;
    add_header Cross-Origin-Opener-Policy same-origin always;
    add_header Cross-Origin-Embedder-Policy require-corp always;
}
```

模型文件较大，建议为 `/models/` 和 `/wasm/` 配置长期缓存，并为 `.wasm` 返回 `application/wasm`。

## 支持格式

- PNG、JPG/JPEG、WEBP、BMP
- 单张图片最大 15 MB
- 默认识别中文和英文印刷体
