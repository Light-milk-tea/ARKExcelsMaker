import { mkdir, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const modelDir = join(root, "public", "models");
const ortVersion = "1.24.3";
const wasmDir = join(root, "public", "wasm", ortVersion);

const models = [
  {
    name: "PP-OCRv5_mobile_det_onnx_infer.tar",
    url: "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_det_onnx_infer.tar",
  },
  {
    name: "PP-OCRv5_mobile_rec_onnx_infer.tar",
    url: "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_rec_onnx_infer.tar",
  },
];

const ortAssets = [
  "ort-wasm-simd-threaded.wasm",
  "ort-wasm-simd-threaded.jsep.wasm",
  "ort-wasm-simd-threaded.mjs",
  "ort-wasm-simd-threaded.jsep.mjs",
].map((name) => ({
  name,
  url: `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ortVersion}/dist/${name}`,
}));

async function download({ name, url }, targetDir, overwrite = false) {
  const target = join(targetDir, name);

  if (!overwrite) {
    try {
      const file = await stat(target);
      if (file.size > 0) {
        console.log(`已存在：${name}`);
        return;
      }
    } catch {
      // 文件不存在时继续下载。
    }
  }

  console.log(`正在下载：${name}`);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`下载 ${name} 失败：HTTP ${response.status}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength === 0) {
    throw new Error(`下载 ${name} 失败：文件为空`);
  }

  await writeFile(target, bytes);
  console.log(`下载完成：${name} (${(bytes.byteLength / 1024 / 1024).toFixed(1)} MB)`);
}

await mkdir(modelDir, { recursive: true });
await mkdir(wasmDir, { recursive: true });
await Promise.all(models.map((asset) => download(asset, modelDir)));
await Promise.all(ortAssets.map((asset) => download(asset, wasmDir, true)));

console.log(`OCR 本地资源准备完成（ONNX Runtime Web ${ortVersion}）。`);
