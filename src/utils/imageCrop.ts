import type { OcrResultItem } from "@paddleocr/paddleocr-js";
import type {
  ImageRect,
  SkillCropConfig,
} from "../types/skill";

export function boundingRect(line: OcrResultItem): ImageRect {
  const xs = line.poly.map(([x]) => x);
  const ys = line.poly.map(([, y]) => y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);

  return {
    x,
    y,
    width: Math.max(...xs) - x,
    height: Math.max(...ys) - y,
  };
}

export function calculateSkillRect(
  nameBox: ImageRect,
  imageWidth: number,
  imageHeight: number,
  config: SkillCropConfig,
  referenceTextHeight = nameBox.height,
): ImageRect | null {
  if (referenceTextHeight <= 0) return null;

  const baseSize = referenceTextHeight * config.iconSizeByTextHeight;
  const padding = baseSize * config.paddingRatio;
  const size = baseSize + padding * 2;
  // 干员名字在界面中右对齐。以最右侧两个字的中心作为技能锚点，
  // 这样两字名字保持居中，较长名字向左扩展时不会带偏技能区域。
  const centerX =
    nameBox.x +
    nameBox.width -
    referenceTextHeight +
    referenceTextHeight * config.horizontalOffsetByTextHeight;
  const x = centerX - size / 2;
  const y =
    nameBox.y -
    referenceTextHeight * config.verticalGapByTextHeight -
    baseSize -
    padding;

  if (
    x < 0 ||
    y < 0 ||
    x + size > imageWidth ||
    y + size > imageHeight
  ) {
    return null;
  }

  return { x, y, width: size, height: size };
}

export function cropToCanvas(
  image: CanvasImageSource,
  rect: ImageRect,
  outputSize = 64,
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = outputSize;
  canvas.height = outputSize;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("浏览器无法创建技能图标画布");
  }

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(
    image,
    rect.x,
    rect.y,
    rect.width,
    rect.height,
    0,
    0,
    outputSize,
    outputSize,
  );

  return canvas;
}
