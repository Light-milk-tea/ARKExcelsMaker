import type { OperatorData } from "../types/skill";

let operatorsPromise: Promise<OperatorData[]> | null = null;

function assetUrl(path: string): string {
  return `${import.meta.env.BASE_URL}${path}`.replace(/\/{2,}/g, "/");
}

export function loadOperators(): Promise<OperatorData[]> {
  if (!operatorsPromise) {
    operatorsPromise = fetch(assetUrl("data/operators.json"))
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`干员技能数据加载失败：HTTP ${response.status}`);
        }
        return (await response.json()) as OperatorData[];
      })
      .then((operators) =>
        operators.filter(
          (operator) =>
            operator.name.trim().length > 0 && operator.skills.length > 0,
        ),
      )
      .catch((error) => {
        operatorsPromise = null;
        throw error;
      });
  }

  return operatorsPromise;
}
