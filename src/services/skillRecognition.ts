import type { OcrResultItem } from "@paddleocr/paddleocr-js";
import { loadOperators } from "../data/operatorIndex";
import type {
  OperatorSkillRecognition,
  SkillCandidate,
  SkillCropConfig,
  SkillRecognitionResult,
} from "../types/skill";
import {
  boundingRect,
  calculateSkillRect,
  cropToCanvas,
} from "../utils/imageCrop";
import { compareSkillImage } from "../utils/imageComparison";
import { matchOperatorName } from "../utils/similarity";

export const DEFAULT_SKILL_CROP_CONFIG: SkillCropConfig = {
  iconSizeByTextHeight: 1.65,
  // 缩小框时同步补偿垂直间距，保持裁剪中心高度基本不变。
  verticalGapByTextHeight: 0,
  horizontalOffsetByTextHeight: 0.2,
  paddingRatio: 0,
};

const MIN_SKILL_SCORE = 0.68;
const MIN_CANDIDATE_GAP = 0.04;
const MIN_NAME_SCORE = 0.64;

export async function recognizeOperatorSkills(
  file: File,
  lines: OcrResultItem[],
  config: SkillCropConfig = DEFAULT_SKILL_CROP_CONFIG,
): Promise<SkillRecognitionResult> {
  const [operators, image] = await Promise.all([
    loadOperators(),
    createImageBitmap(file),
  ]);

  try {
    const items: OperatorSkillRecognition[] = [];
    const seen = new Set<string>();
    const matchedNameHeights = lines
      .filter((line) => {
        const match = matchOperatorName(line.text, operators);
        return (
          match.name !== null &&
          match.confidence >= MIN_NAME_SCORE &&
          match.operators.length > 0
        );
      })
      .map((line) => boundingRect(line).height)
      .filter((height) => Number.isFinite(height) && height > 0)
      .sort((left, right) => left - right);
    const middle = Math.floor(matchedNameHeights.length / 2);
    const medianTextHeight =
      matchedNameHeights.length % 2 === 0
        ? ((matchedNameHeights[middle - 1] ?? 0) +
            (matchedNameHeights[middle] ?? 0)) /
          2
        : (matchedNameHeights[middle] ?? 0);

    for (const line of lines) {
      const nameMatch = matchOperatorName(line.text, operators);
      if (
        !nameMatch.name ||
        nameMatch.confidence < MIN_NAME_SCORE ||
        nameMatch.operators.length === 0
      ) {
        continue;
      }

      const nameBox = boundingRect(line);
      const dedupeKey = `${nameMatch.name}:${Math.round(nameBox.x / 10)}:${Math.round(nameBox.y / 10)}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);

      const cropRect = calculateSkillRect(
        nameBox,
        image.width,
        image.height,
        config,
        medianTextHeight || nameBox.height,
      );
      const skills = [
        ...new Map(
          nameMatch.operators
            .flatMap((operator) => operator.skills)
            .map((skill) => [skill.skillId, skill]),
        ).values(),
      ];

      if (skills.length === 0) {
        items.push({
          rawText: line.text,
          matchedName: nameMatch.name,
          operatorIds: nameMatch.operators.map(
            (operator) => operator.characterId,
          ),
          nameConfidence: nameMatch.confidence,
          ocrConfidence: line.score,
          nameBox,
          cropRect,
          cropDataUrl: null,
          status: "no-skills",
          best: null,
          candidates: [],
        });
        continue;
      }

      if (!cropRect) {
        items.push({
          rawText: line.text,
          matchedName: nameMatch.name,
          operatorIds: nameMatch.operators.map(
            (operator) => operator.characterId,
          ),
          nameConfidence: nameMatch.confidence,
          ocrConfidence: line.score,
          nameBox,
          cropRect: null,
          cropDataUrl: null,
          status: "out-of-bounds",
          best: null,
          candidates: [],
        });
        continue;
      }

      // 以 128px 无损裁剪保留细节；哈希计算阶段再按算法要求缩放。
      const cropCanvas = cropToCanvas(image, cropRect, 128);
      const candidates: SkillCandidate[] = (
        await Promise.all(
          skills.map(async (skill) => {
            const similarity = await compareSkillImage(cropCanvas, skill);
            return {
              skill,
              ...similarity,
            };
          }),
        )
      ).sort((left, right) => right.score - left.score);

      const best = candidates[0] ?? null;
      const second = candidates[1] ?? null;
      let status: OperatorSkillRecognition["status"] = "matched";

      if (nameMatch.confidence < 0.75) {
        status = "name-uncertain";
      } else if (!best || best.score < MIN_SKILL_SCORE) {
        status = "low-confidence";
      } else if (second && best.score - second.score < MIN_CANDIDATE_GAP) {
        status = "ambiguous";
      }

      items.push({
        rawText: line.text,
        matchedName: nameMatch.name,
        operatorIds: nameMatch.operators.map(
          (operator) => operator.characterId,
        ),
        nameConfidence: nameMatch.confidence,
        ocrConfidence: line.score,
        nameBox,
        cropRect,
        cropDataUrl: cropCanvas.toDataURL("image/png"),
        status,
        best,
        candidates: candidates.slice(0, 3),
      });
    }

    return {
      items,
      config: { ...config },
      image: { width: image.width, height: image.height },
    };
  } finally {
    image.close();
  }
}
