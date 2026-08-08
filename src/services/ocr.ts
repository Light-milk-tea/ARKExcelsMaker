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

const baseUrl = import.meta.env.BASE_URL;
const ASSET_FETCH_TIMEOUT_MS = 5 * 60 * 1000;

const DET_MODEL = "models/PP-OCRv5_mobile_det_onnx_infer.tar";
const REC_MODEL = "models/PP-OCRv5_mobile_rec_onnx_infer.tar";

let instance: OcrInstance | null = null;
let initialization: Promise<OcrInstance> | null = null;
let loadStage: OcrLoadStage = "models";
const loadStageListeners = new Set<(stage: OcrLoadStage) => void>();

function setLoadStage(stage: OcrLoadStage) {
  loadStage = stage;
  for (const listener of loadStageListeners) {
    listener(stage);
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
  // jsep 体积约 24MB，仅 WebGPU 需要；普通 HTTP/WASM 用约 12MB 版本，降低首次超时概率。
  const wasmFile = webgpu
    ? "ort-wasm-simd-threaded.jsep.wasm"
    : "ort-wasm-simd-threaded.wasm";

  return {
    backend: webgpu ? ("auto" as const) : ("wasm" as const),
    wasmUrl: localAsset(`wasm/1.24.3/${wasmFile}`),
    wasmPaths: {
      wasm: localAsset(`wasm/1.24.3/${wasmFile}`),
    } as unknown as string,
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

async function preloadAssets(wasmUrl: string): Promise<void> {
  setLoadStage("models");
  await Promise.all([
    fetchWithTimeout(localAsset(DET_MODEL), ASSET_FETCH_TIMEOUT_MS),
    fetchWithTimeout(localAsset(REC_MODEL), ASSET_FETCH_TIMEOUT_MS),
  ]);

  setLoadStage("runtime");
  await fetchWithTimeout(wasmUrl, ASSET_FETCH_TIMEOUT_MS);
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
      await preloadAssets(runtime.wasmUrl);

      setLoadStage("session");
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
          // 仅覆盖 WASM 地址，让 Worker 使用其内置且版本完全匹配的 JS glue。
          // 这样可避免 Vite 拦截 public 目录中的动态 .mjs 导入。
          wasmPaths: runtime.wasmPaths,
          // 单线程可在 iframe、非跨源隔离页面及普通静态托管中稳定运行。
          numThreads: 1,
          simd: true,
        },
      });
      instance = ocr;
      return ocr;
    })().catch((error) => {
      initialization = null;
      throw error;
    });
  }

  return initialization;
}

export async function recognizeImage(file: File): Promise<RecognitionResult> {
  try {
    const ocr = await getOcr();
    const [result] = await ocr.predict(file, {
      textRecScoreThresh: 0.45,
    });

    if (!result) {
      throw new Error("OCR 没有返回识别结果");
    }

    const lines = result.items.filter((item) => item.text.trim().length > 0);

    return {
      text: lines.map((item) => item.text.trim()).join("\n"),
      lines,
      elapsedMs: result.metrics.totalMs,
      provider: result.runtime.recProvider,
      image: result.image,
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
