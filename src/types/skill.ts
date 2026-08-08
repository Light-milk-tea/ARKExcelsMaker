import type { OcrResultItem } from "@paddleocr/paddleocr-js";

export interface SkillData {
  skillId: string;
  name: string;
  icon: string;
  iconKey: string;
  hash: string;
  colorFeature: [number, number, number];
}

export interface OperatorData {
  characterId: string;
  name: string;
  profession: string;
  rarity: number | null;
  isNotObtainable: boolean;
  appellation: string | null;
  skills: SkillData[];
}

export interface SkillCropConfig {
  iconSizeByTextHeight: number;
  verticalGapByTextHeight: number;
  horizontalOffsetByTextHeight: number;
  paddingRatio: number;
}

export interface ImageRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SkillCandidate {
  skill: SkillData;
  score: number;
  edgeSimilarity: number;
  pixelSimilarity: number;
  hashSimilarity: number;
  colorSimilarity: number;
}

export type SkillRecognitionStatus =
  | "matched"
  | "low-confidence"
  | "ambiguous"
  | "name-uncertain"
  | "out-of-bounds"
  | "no-skills";

export interface OperatorSkillRecognition {
  rawText: string;
  matchedName: string | null;
  operatorIds: string[];
  nameConfidence: number;
  ocrConfidence: number;
  nameBox: ImageRect;
  cropRect: ImageRect | null;
  cropDataUrl: string | null;
  status: SkillRecognitionStatus;
  best: SkillCandidate | null;
  candidates: SkillCandidate[];
}

export interface SkillRecognitionResult {
  items: OperatorSkillRecognition[];
  config: SkillCropConfig;
  image: {
    width: number;
    height: number;
  };
}

export interface MatchedOperatorName {
  rawText: string;
  name: string | null;
  confidence: number;
  operators: OperatorData[];
  line: OcrResultItem;
}
