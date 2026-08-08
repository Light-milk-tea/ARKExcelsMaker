import type { OperatorData } from "../types/skill";

const IGNORED_TEXT = /[\s·•,，。.!！?？:：;；"'“”‘’()（）[\]【】]/g;

export function normalizeRecognizedText(text: string): string {
  return text.replace(IGNORED_TEXT, "").trim();
}

export function levenshteinDistance(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  const previous = Array.from({ length: b.length + 1 }, (_, index) => index);

  for (let i = 1; i <= a.length; i += 1) {
    const current = [i];
    for (let j = 1; j <= b.length; j += 1) {
      current[j] = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    previous.splice(0, previous.length, ...current);
  }

  return previous[b.length];
}

export interface NameMatch {
  name: string | null;
  confidence: number;
  operators: OperatorData[];
}

export function matchOperatorName(
  rawText: string,
  operators: OperatorData[],
): NameMatch {
  const normalized = normalizeRecognizedText(rawText);
  if (!normalized) {
    return { name: null, confidence: 0, operators: [] };
  }

  const byName = new Map<string, OperatorData[]>();
  for (const operator of operators) {
    const list = byName.get(operator.name) ?? [];
    list.push(operator);
    byName.set(operator.name, list);
  }

  const scored = [...byName.entries()]
    .map(([name, entries]) => {
      const normalizedName = normalizeRecognizedText(name);
      const exactContained =
        normalized.length >= 2 &&
        normalizedName.length >= 2 &&
        (normalized.includes(normalizedName) ||
          normalizedName.includes(normalized));
      const distance = levenshteinDistance(normalized, normalizedName);
      const denominator = Math.max(normalized.length, normalizedName.length, 1);
      const confidence = exactContained
        ? normalized === normalizedName
          ? 1
          : 0.92
        : Math.max(0, 1 - distance / denominator);
      return { name, operators: entries, confidence };
    })
    .sort((a, b) => b.confidence - a.confidence);

  const best = scored[0];
  const second = scored[1];
  if (!best || best.confidence < 0.64) {
    return { name: null, confidence: best?.confidence ?? 0, operators: [] };
  }

  if (
    best.confidence < 1 &&
    second &&
    best.confidence - second.confidence < 0.15
  ) {
    return { name: null, confidence: best.confidence, operators: [] };
  }

  return best;
}

export function hashSimilarity(a: string, b: string): number {
  const length = Math.max(a.length, b.length);
  if (length === 0) return 0;

  let differentBits = 0;
  for (let i = 0; i < length; i += 1) {
    const left = Number.parseInt(a[i] ?? "0", 16);
    const right = Number.parseInt(b[i] ?? "0", 16);
    let xor = left ^ right;
    while (xor > 0) {
      differentBits += xor & 1;
      xor >>= 1;
    }
  }

  return Math.max(0, 1 - differentBits / (length * 4));
}

export function colorSimilarity(
  a: readonly number[],
  b: readonly number[],
): number {
  const distance = Math.sqrt(
    a.reduce((sum, value, index) => {
      const difference = value - (b[index] ?? 0);
      return sum + difference * difference;
    }, 0),
  );

  return Math.max(0, 1 - distance / Math.sqrt(3));
}
