import type { SkillData } from "../types/skill";
import { hashSimilarity } from "./similarity";
import { computeImageFeatures } from "./imageHash";

interface DetailedImageFeatures {
  gray: Float32Array;
  edges: Float32Array;
  colorHistogram: Float32Array;
  hash: string;
}

export interface DetailedSimilarity {
  score: number;
  edgeSimilarity: number;
  pixelSimilarity: number;
  colorSimilarity: number;
  hashSimilarity: number;
}

const SIZE = 64;
const SAMPLE_MARGIN = 4;
const imageCache = new Map<string, Promise<HTMLImageElement>>();
const standardFeatureCache = new Map<string, Promise<DetailedImageFeatures>>();

function resolveAsset(path: string): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, "")}`.replace(
    /\/{2,}/g,
    "/",
  );
}

function loadImage(path: string): Promise<HTMLImageElement> {
  const url = resolveAsset(path);
  let promise = imageCache.get(url);
  if (!promise) {
    promise = new Promise((resolve, reject) => {
      const image = new Image();
      image.decoding = "async";
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error(`技能图标加载失败：${path}`));
      image.src = url;
    });
    imageCache.set(url, promise);
  }
  return promise;
}

function renderVariant(
  source: CanvasImageSource,
  sourceWidth: number,
  sourceHeight: number,
  scale = 1,
  offsetX = 0,
  offsetY = 0,
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("浏览器无法创建图像比较画布");

  context.fillStyle = "#000";
  context.fillRect(0, 0, SIZE, SIZE);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";

  const renderedSize = SIZE * scale;
  context.drawImage(
    source,
    0,
    0,
    sourceWidth,
    sourceHeight,
    (SIZE - renderedSize) / 2 + offsetX,
    (SIZE - renderedSize) / 2 + offsetY,
    renderedSize,
    renderedSize,
  );
  return canvas;
}

function extractDetailedFeatures(
  source: CanvasImageSource,
  width: number,
  height: number,
): DetailedImageFeatures {
  const canvas = renderVariant(source, width, height);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("浏览器无法读取图像比较画布");
  const pixels = context.getImageData(0, 0, SIZE, SIZE).data;
  const fullGray = new Float32Array(SIZE * SIZE);
  const colorHistogram = new Float32Array(24);
  let sampledPixels = 0;

  for (let y = 0; y < SIZE; y += 1) {
    for (let x = 0; x < SIZE; x += 1) {
      const pixelIndex = y * SIZE + x;
      const offset = pixelIndex * 4;
      const r = pixels[offset] / 255;
      const g = pixels[offset + 1] / 255;
      const b = pixels[offset + 2] / 255;
      fullGray[pixelIndex] = r * 0.299 + g * 0.587 + b * 0.114;

      if (
        x >= SAMPLE_MARGIN &&
        x < SIZE - SAMPLE_MARGIN &&
        y >= SAMPLE_MARGIN &&
        y < SIZE - SAMPLE_MARGIN
      ) {
        colorHistogram[Math.min(7, Math.floor(r * 8))] += 1;
        colorHistogram[8 + Math.min(7, Math.floor(g * 8))] += 1;
        colorHistogram[16 + Math.min(7, Math.floor(b * 8))] += 1;
        sampledPixels += 1;
      }
    }
  }

  const valuesPerSide = SIZE - SAMPLE_MARGIN * 2;
  const gray = new Float32Array(valuesPerSide * valuesPerSide);
  const edges = new Float32Array(valuesPerSide * valuesPerSide);
  let outputIndex = 0;

  for (let y = SAMPLE_MARGIN; y < SIZE - SAMPLE_MARGIN; y += 1) {
    for (let x = SAMPLE_MARGIN; x < SIZE - SAMPLE_MARGIN; x += 1) {
      gray[outputIndex] = fullGray[y * SIZE + x];

      const topLeft = fullGray[(y - 1) * SIZE + x - 1];
      const top = fullGray[(y - 1) * SIZE + x];
      const topRight = fullGray[(y - 1) * SIZE + x + 1];
      const left = fullGray[y * SIZE + x - 1];
      const right = fullGray[y * SIZE + x + 1];
      const bottomLeft = fullGray[(y + 1) * SIZE + x - 1];
      const bottom = fullGray[(y + 1) * SIZE + x];
      const bottomRight = fullGray[(y + 1) * SIZE + x + 1];
      const gradientX =
        -topLeft + topRight - 2 * left + 2 * right - bottomLeft + bottomRight;
      const gradientY =
        -topLeft - 2 * top - topRight + bottomLeft + 2 * bottom + bottomRight;
      edges[outputIndex] = Math.sqrt(
        gradientX * gradientX + gradientY * gradientY,
      );
      outputIndex += 1;
    }
  }

  for (let index = 0; index < colorHistogram.length; index += 1) {
    colorHistogram[index] /= sampledPixels;
  }

  const simple = computeImageFeatures(canvas, SIZE, SIZE);
  return {
    gray,
    edges,
    colorHistogram,
    hash: simple.hash,
  };
}

function normalizedCorrelation(
  left: Float32Array,
  right: Float32Array,
): number {
  const length = Math.min(left.length, right.length);
  if (length === 0) return 0;

  let leftMean = 0;
  let rightMean = 0;
  for (let index = 0; index < length; index += 1) {
    leftMean += left[index];
    rightMean += right[index];
  }
  leftMean /= length;
  rightMean /= length;

  let covariance = 0;
  let leftVariance = 0;
  let rightVariance = 0;
  for (let index = 0; index < length; index += 1) {
    const leftDelta = left[index] - leftMean;
    const rightDelta = right[index] - rightMean;
    covariance += leftDelta * rightDelta;
    leftVariance += leftDelta * leftDelta;
    rightVariance += rightDelta * rightDelta;
  }

  const denominator = Math.sqrt(leftVariance * rightVariance);
  if (denominator < 1e-8) return 0;
  const correlation = covariance / denominator;
  return Math.max(0, Math.min(1, (correlation + 1) / 2));
}

function histogramSimilarity(
  left: Float32Array,
  right: Float32Array,
): number {
  const length = Math.min(left.length, right.length);
  let intersection = 0;
  for (let index = 0; index < length; index += 1) {
    intersection += Math.min(left[index], right[index]);
  }
  // 三个颜色通道的直方图分别归一化，总交集最大为 3。
  return Math.max(0, Math.min(1, intersection / 3));
}

function compareFeatures(
  screenshot: DetailedImageFeatures,
  standard: DetailedImageFeatures,
  storedSkill: SkillData,
): DetailedSimilarity {
  const edgeScore = normalizedCorrelation(screenshot.edges, standard.edges);
  const pixelScore = normalizedCorrelation(screenshot.gray, standard.gray);
  const colorScore = histogramSimilarity(
    screenshot.colorHistogram,
    standard.colorHistogram,
  );
  const hashScore = hashSimilarity(screenshot.hash, storedSkill.hash);

  return {
    score: edgeScore * 0.40 + pixelScore * 0.30 + hashScore * 0.20 + colorScore * 0.10,
    edgeSimilarity: edgeScore,
    pixelSimilarity: pixelScore,
    colorSimilarity: colorScore,
    hashSimilarity: hashScore,
  };
}

async function getStandardFeatures(
  skill: SkillData,
): Promise<DetailedImageFeatures> {
  let promise = standardFeatureCache.get(skill.icon);
  if (!promise) {
    promise = loadImage(skill.icon).then((image) =>
      extractDetailedFeatures(
        image,
        image.naturalWidth || SIZE,
        image.naturalHeight || SIZE,
      ),
    );
    standardFeatureCache.set(skill.icon, promise);
  }
  return promise;
}

export async function compareSkillImage(
  crop: HTMLCanvasElement,
  skill: SkillData,
): Promise<DetailedSimilarity> {
  const standard = await getStandardFeatures(skill);
  const scales = [0.94, 1, 1.06];
  const offsets = [-2, 0, 2];
  let best: DetailedSimilarity | null = null;

  for (const scale of scales) {
    for (const offsetX of offsets) {
      for (const offsetY of offsets) {
        const variant = renderVariant(
          crop,
          crop.width,
          crop.height,
          scale,
          offsetX,
          offsetY,
        );
        const screenshot = extractDetailedFeatures(variant, SIZE, SIZE);
        const result = compareFeatures(screenshot, standard, skill);
        if (!best || result.score > best.score) best = result;
      }
    }
  }

  if (!best) throw new Error("无法生成技能图标比较结果");
  console.log(`[技能对比] ${skill.name} | 边缘:${best.edgeSimilarity.toFixed(3)} 像素:${best.pixelSimilarity.toFixed(3)} 哈希:${best.hashSimilarity.toFixed(3)} 颜色:${best.colorSimilarity.toFixed(3)} → 总分:${best.score.toFixed(3)}`);
  return best;
}
