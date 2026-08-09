import {
  PaddleOCR,
  type InitializationSummary,
  type OcrResultItem,
} from "@paddleocr/paddleocr-js";

type OcrInstance = Awaited<ReturnType<typeof PaddleOCR.create>>;

export interface RecognitionResult {
  text: string;
  lines: OcrResultItem[];
  elapsedMs: number;
  provider: string;
  image: {
    width: number;
    height: number;
  };
}

export type OcrLoadStage = "models" | "runtime" | "session";

export interface OcrProgress {
  stage: string;
  percent: number;
}

const baseUrl = import.meta.env.BASE_URL;
const ASSET_FETCH_TIMEOUT_MS = 5 * 60 * 1000;

const DET_MODEL = "models/PP-OCRv5_mobile_det_onnx_infer.tar";
const REC_MODEL = "models/PP-OCRv5_mobile_rec_onnx_infer.tar";

// 编队截图常见约 720p；短边低于此值时先放大，减轻边缘小字名条漏检。
const OCR_TARGET_MIN_SIDE = 960;
const OCR_MAX_SCALE = 2.5;

let instance: OcrInstance | null = null;
let initialization: Promise<OcrInstance> | null = null;
let loadStage: OcrLoadStage = "models";
const loadStageListeners = new Set<(stage: OcrLoadStage) => void>();

// 进度追踪
let currentProgress: OcrProgress = { stage: "", percent: 0 };
const progressListeners = new Set<(progress: OcrProgress) => void>();

function setLoadStage(stage: OcrLoadStage) {
  loadStage = stage;
  for (const listener of loadStageListeners) {
    listener(stage);
  }
}

function setProgress(stage: string, percent: number) {
  currentProgress = { stage, percent };
  for (const listener of progressListeners) {
    listener(currentProgress);
  }
}

export function subscribeOcrLoadStage(
  listener: (stage: OcrLoadStage) => void,
): () => void {
  loadStageListeners.add(listener);
  listener(loadStage);
  return () => {
    loadStageListeners.delete(listener);
  };
}

export function subscribeOcrProgress(
  listener: (progress: OcrProgress) => void,
): () => void {
  progressListeners.add(listener);
  listener(currentProgress);
  return () => {
    progressListeners.delete(listener);
  };
}

function localAsset(path: string): string {
  return `${baseUrl}${path}`.replace(/\/{2,}/g, "/");
}

function canUseWebGpu(): boolean {
  return (
    window.isSecureContext &&
    typeof navigator !== "undefined" &&
    typeof navigator.gpu?.requestAdapter === "function"
  );
}

function resolveRuntimeAssets() {
  const webgpu = canUseWebGpu();
  return {
    backend: webgpu ? ("auto" as const) : ("wasm" as const),
  };
}

async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}：${url}`);
    }
    // 读完 body，确保写入浏览器 HTTP 缓存，供后续 ORT / 模型加载复用。
    await response.arrayBuffer();
    return response;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(
        `资源下载超时（>${Math.round(timeoutMs / 1000)}s）：${url}。请检查服务器对大文件的传输是否正常。`,
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchWithProgress(
  url: string,
  label: string,
  percentBase: number,
  percentRange: number,
): Promise<Response> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}：${url}`);
  }
  const contentLength = Number(response.headers.get("content-length")) || 0;
  const reader = response.body?.getReader();
  if (!contentLength || !reader) {
    // 无法获取大小，直接读完
    setProgress(label, percentBase + percentRange);
    const buf = await response.arrayBuffer();
    return new Response(buf, { headers: response.headers });
  }
  let received = 0;
  const chunks: Uint8Array[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    const pct = percentBase + Math.round((received / contentLength) * percentRange);
    setProgress(label, Math.min(pct, percentBase + percentRange));
  }
  const all = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    all.set(chunk, offset);
    offset += chunk.length;
  }
  return new Response(all, { headers: response.headers });
}

async function preloadAssets(): Promise<void> {
  setLoadStage("models");
  await fetchWithProgress(localAsset(DET_MODEL), "正在下载检测模型...", 0, 40);
  await fetchWithProgress(localAsset(REC_MODEL), "正在下载识别模型...", 40, 40);
}

export async function initializeOcr(): Promise<InitializationSummary | null> {
  const ocr = await getOcr();
  return ocr.getInitializationSummary();
}

async function getOcr(): Promise<OcrInstance> {
  if (instance) {
    return instance;
  }

  if (!initialization) {
    initialization = (async () => {
      const runtime = resolveRuntimeAssets();
      await preloadAssets();

      setLoadStage("session");
      setProgress("正在初始化识图引擎...", 80);
      const ocr = await PaddleOCR.create({
        worker: true,
        textDetectionModelName: "PP-OCRv5_mobile_det",
        textDetectionModelAsset: {
          url: localAsset(DET_MODEL),
        },
        textRecognitionModelName: "PP-OCRv5_mobile_rec",
        textRecognitionModelAsset: {
          url: localAsset(REC_MODEL),
        },
        ortOptions: {
          backend: runtime.backend,
          numThreads: 1,
          simd: true,
        },
      });
      setProgress("", 100);
      instance = ocr;
      return ocr;
    })().catch((error) => {
      initialization = null;
      throw error;
    });
  }

  return initialization;
}

interface PreparedOcrInput {
  source: File | HTMLCanvasElement;
  scale: number;
  original: { width: number; height: number };
}

async function prepareOcrInput(file: File): Promise<PreparedOcrInput> {
  const bitmap = await createImageBitmap(file);
  try {
    const { width, height } = bitmap;
    const minSide = Math.min(width, height);
    const scale =
      minSide > 0
        ? Math.min(OCR_MAX_SCALE, Math.max(1, OCR_TARGET_MIN_SIDE / minSide))
        : 1;

    if (scale <= 1.01) {
      return { source: file, scale: 1, original: { width, height } };
    }

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("浏览器无法创建 OCR 预处理画布");
    }

    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

    return {
      source: canvas,
      scale,
      original: { width, height },
    };
  } finally {
    bitmap.close();
  }
}

function mapLinesToOriginal(
  lines: OcrResultItem[],
  scale: number,
): OcrResultItem[] {
  if (scale === 1) {
    return lines;
  }

  return lines.map((item) => ({
    ...item,
    poly: item.poly.map(([x, y]) => [x / scale, y / scale] as [number, number]),
  }));
}

export async function recognizeImage(file: File): Promise<RecognitionResult> {
  try {
    const ocr = await getOcr();
    const prepared = await prepareOcrInput(file);
    const [result] = await ocr.predict(prepared.source, {
      // 诊断结论：默认检测对左下角小字名条偏保守；略降阈值并提高检测输入边长。
      textRecScoreThresh: 0.4,
      textDetThresh: 0.2,
      textDetBoxThresh: 0.5,
      textDetUnclipRatio: 1.8,
      textDetLimitType: "min",
      textDetLimitSideLen: 1280,
    });

    if (!result) {
      throw new Error("OCR 没有返回识别结果");
    }

    const lines = mapLinesToOriginal(
      result.items.filter((item) => item.text.trim().length > 0),
      prepared.scale,
    );

    return {
      text: lines.map((item) => item.text.trim()).join("\n"),
      lines,
      elapsedMs: result.metrics.totalMs,
      provider: result.runtime.recProvider,
      // 技能裁剪基于原图；坐标已映射回原图尺寸。
      image: prepared.original,
    };
  } catch (error) {
    throw new Error(toFriendlyError(error));
  }
}

export async function disposeOcr(): Promise<void> {
  const ocr = instance;
  instance = null;
  initialization = null;
  setLoadStage("models");
  await ocr?.dispose();
}

function toFriendlyError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);

  if (/资源下载超时|timed out after/i.test(message)) {
    return (
      "OCR 资源加载超时。当前站点大文件（模型/WASM）下载过慢或不完整。" +
      "请检查 Nginx/带宽，或将 /models 与 /wasm 放到对象存储/CDN 后重试。"
    );
  }

  if (/fetch|network|http|load|AbortError/i.test(message)) {
    return "OCR 资源加载失败，请确认服务器上 models 与 wasm 文件完整且可访问。";
  }

  if (/webgpu/i.test(message)) {
    return "WebGPU 初始化失败，请更新浏览器，或确认当前页面通过 HTTPS/localhost 访问。";
  }

  if (/memory|allocation|out of/i.test(message)) {
    return "浏览器内存不足，请换用尺寸更小的图片后重试。";
  }

  return `识别失败：${message}`;
}
