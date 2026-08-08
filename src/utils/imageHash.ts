export interface ImageFeatures {
  hash: string;
  colorFeature: [number, number, number];
}

const HASH_WIDTH = 9;
const HASH_HEIGHT = 8;

export function computeImageFeatures(
  source: CanvasImageSource,
  width: number,
  height: number,
): ImageFeatures {
  const colorCanvas = document.createElement("canvas");
  colorCanvas.width = 64;
  colorCanvas.height = 64;
  const colorContext = colorCanvas.getContext("2d", {
    willReadFrequently: true,
  });
  if (!colorContext) {
    throw new Error("浏览器无法创建图像处理画布");
  }

  colorContext.drawImage(source, 0, 0, width, height, 0, 0, 64, 64);
  const pixels = colorContext.getImageData(0, 0, 64, 64).data;
  const pixelCount = 64 * 64;
  let red = 0;
  let green = 0;
  let blue = 0;

  for (let i = 0; i < pixels.length; i += 4) {
    const alpha = pixels[i + 3] / 255;
    red += (pixels[i] / 255) * alpha;
    green += (pixels[i + 1] / 255) * alpha;
    blue += (pixels[i + 2] / 255) * alpha;
  }

  const hashCanvas = document.createElement("canvas");
  hashCanvas.width = HASH_WIDTH;
  hashCanvas.height = HASH_HEIGHT;
  const hashContext = hashCanvas.getContext("2d", {
    willReadFrequently: true,
  });
  if (!hashContext) {
    throw new Error("浏览器无法创建哈希画布");
  }

  hashContext.drawImage(
    source,
    0,
    0,
    width,
    height,
    0,
    0,
    HASH_WIDTH,
    HASH_HEIGHT,
  );
  const hashPixels = hashContext.getImageData(
    0,
    0,
    HASH_WIDTH,
    HASH_HEIGHT,
  ).data;

  let bits = "";
  for (let y = 0; y < HASH_HEIGHT; y += 1) {
    for (let x = 0; x < HASH_WIDTH - 1; x += 1) {
      const leftIndex = (y * HASH_WIDTH + x) * 4;
      const rightIndex = leftIndex + 4;
      const left =
        hashPixels[leftIndex] * 0.299 +
        hashPixels[leftIndex + 1] * 0.587 +
        hashPixels[leftIndex + 2] * 0.114;
      const right =
        hashPixels[rightIndex] * 0.299 +
        hashPixels[rightIndex + 1] * 0.587 +
        hashPixels[rightIndex + 2] * 0.114;
      bits += left < right ? "1" : "0";
    }
  }

  let hash = "";
  for (let index = 0; index < bits.length; index += 4) {
    hash += Number.parseInt(bits.slice(index, index + 4), 2).toString(16);
  }

  return {
    hash,
    colorFeature: [
      Number((red / pixelCount).toFixed(4)),
      Number((green / pixelCount).toFixed(4)),
      Number((blue / pixelCount).toFixed(4)),
    ],
  };
}
