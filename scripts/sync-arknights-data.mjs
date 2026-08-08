import { createHash } from "node:crypto";
import {
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const cacheDir = join(root, ".cache", "arknights");
const skillSourceDir = join(cacheDir, "skill");
const excelDir = join(cacheDir, "excel");
const outSkillsDir = join(root, "public", "skills");
const outDataDir = join(root, "public", "data");
const reportDir = join(root, "reports");

const SOURCE = "yuanyan3060/ArknightsGameResource";
const RAW_BASE =
  "https://raw.githubusercontent.com/yuanyan3060/ArknightsGameResource/main";
const ICON_SIZE = 64;
const HASH_SIZE = 8;
const DOWNLOAD_CONCURRENCY = 12;

const USER_AGENT = "ocr-local-sync/0.1 (personal learning; skill icon index)";

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

const FORCE_REFRESH = process.env.FORCE_REFRESH === "1";

async function fetchBuffer(url) {
  const response = await fetch(url, {
    headers: { "User-Agent": USER_AGENT },
  });
  if (!response.ok) {
    throw new Error(`下载失败 ${url}: HTTP ${response.status}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

async function fetchText(url, retries = 3) {
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: { "User-Agent": USER_AGENT },
      });
      if (!response.ok) {
        throw new Error(`下载失败 ${url}: HTTP ${response.status}`);
      }
      return await response.text();
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 800 * (attempt + 1)));
    }
  }
  throw lastError;
}

async function downloadJson(name) {
  await mkdir(excelDir, { recursive: true });
  const target = join(excelDir, name);
  const legacy = join(cacheDir, name);

  if (!FORCE_REFRESH && (await exists(target))) {
    console.log(`使用缓存：${name}`);
    return JSON.parse(await readFile(target, "utf8"));
  }

  if (!FORCE_REFRESH && (await exists(legacy))) {
    console.log(`使用旧缓存：${name}`);
    const text = await readFile(legacy, "utf8");
    await writeFile(target, text);
    return JSON.parse(text);
  }

  console.log(`下载 ${name}`);
  const text = await fetchText(`${RAW_BASE}/gamedata/excel/${name}`);
  await writeFile(target, text);
  return JSON.parse(text);
}

async function resolveCommitSha() {
  try {
    const response = await fetch(
      "https://api.github.com/repos/yuanyan3060/ArknightsGameResource/commits/main",
      {
        headers: {
          "User-Agent": USER_AGENT,
          Accept: "application/vnd.github+json",
        },
      },
    );
    if (!response.ok) return "unknown";
    const json = await response.json();
    return json.sha ?? "unknown";
  } catch {
    return "unknown";
  }
}

function asIconKey(value) {
  if (!value) return null;
  return String(value);
}

/** 用于本地 WebP 与网页路径，避免 URL 中出现方括号。 */
function sanitizeFileStem(value) {
  return String(value).replace(/\[/g, "-").replace(/\]/g, "");
}

function candidateIconKeys(skillId, skillDef, skillRef) {
  const keys = [skillDef?.iconId, skillRef?.overridePrefabKey, skillId]
    .map(asIconKey)
    .filter(Boolean);
  return [...new Set(keys)];
}

function iconFileName(iconKey) {
  return `skill_icon_${iconKey}.png`;
}

function iconRawUrl(iconKey) {
  const fileName = iconFileName(iconKey);
  const encoded = fileName.replace(/\[/g, "%5B").replace(/\]/g, "%5D");
  return `${RAW_BASE}/skill/${encoded}`;
}

function isOperatorEntry(characterId, character) {
  if (!characterId.startsWith("char_")) return false;
  if (character.profession === "TOKEN" || character.profession === "TRAP") {
    return false;
  }
  if (!character.name || !String(character.name).trim()) return false;
  return true;
}

function collectOperators(characterTable, patchTable) {
  const retained = [];
  const excluded = [];
  const noSkills = [];

  const merged = { ...characterTable };
  for (const [id, character] of Object.entries(patchTable.patchChars || {})) {
    merged[id] = character;
  }

  for (const [characterId, character] of Object.entries(merged)) {
    if (!isOperatorEntry(characterId, character)) {
      excluded.push({
        characterId,
        name: character?.name ?? null,
        profession: character?.profession ?? null,
        reason: !characterId.startsWith("char_")
          ? "non_char_prefix"
          : character.profession === "TOKEN" || character.profession === "TRAP"
            ? "token_or_trap"
            : "missing_name",
      });
      continue;
    }

    const skills = Array.isArray(character.skills) ? character.skills : [];
    if (skills.length === 0) {
      noSkills.push({ characterId, name: character.name });
    }

    retained.push({
      characterId,
      name: character.name,
      profession: character.profession,
      rarity: character.rarity ?? null,
      isNotObtainable: Boolean(character.isNotObtainable),
      appellation: character.appellation ?? null,
      skills,
    });
  }

  retained.sort((a, b) => a.characterId.localeCompare(b.characterId));
  return { retained, excluded, noSkills };
}

async function mapPool(items, concurrency, worker) {
  const results = new Array(items.length);
  let index = 0;

  async function run() {
    while (index < items.length) {
      const current = index;
      index += 1;
      results[current] = await worker(items[current], current);
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, () => run()),
  );
  return results;
}

async function downloadIconIfNeeded(iconKey, retries = 2) {
  const fileName = iconFileName(iconKey);
  // Windows 允许文件名含 []，与上游仓库保持一致便于核对。
  const target = join(skillSourceDir, fileName);
  if (await exists(target)) {
    return { iconKey, fileName, ok: true, skipped: true };
  }

  const url = iconRawUrl(iconKey);
  let lastError = "";
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const bytes = await fetchBuffer(url);
      if (bytes.byteLength === 0) {
        lastError = "empty file";
        continue;
      }
      await writeFile(target, bytes);
      return { iconKey, fileName, ok: true, skipped: false };
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      if (lastError.includes("HTTP 404")) break;
      await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)));
    }
  }

  return { iconKey, fileName, ok: false, error: lastError };
}

async function computeFeatures(pngPath) {
  const { data, info } = await sharp(pngPath)
    .resize(ICON_SIZE, ICON_SIZE, { fit: "fill" })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const pixelCount = info.width * info.height;
  let rSum = 0;
  let gSum = 0;
  let bSum = 0;

  for (let i = 0; i < pixelCount; i += 1) {
    const offset = i * 4;
    const alpha = data[offset + 3] / 255;
    rSum += (data[offset] / 255) * alpha;
    gSum += (data[offset + 1] / 255) * alpha;
    bSum += (data[offset + 2] / 255) * alpha;
  }

  const colorFeature = [
    Number((rSum / pixelCount).toFixed(4)),
    Number((gSum / pixelCount).toFixed(4)),
    Number((bSum / pixelCount).toFixed(4)),
  ];

  const gray = await sharp(pngPath)
    .resize(HASH_SIZE + 1, HASH_SIZE, { fit: "fill" })
    .grayscale()
    .raw()
    .toBuffer();

  let bits = "";
  for (let y = 0; y < HASH_SIZE; y += 1) {
    for (let x = 0; x < HASH_SIZE; x += 1) {
      const left = gray[y * (HASH_SIZE + 1) + x];
      const right = gray[y * (HASH_SIZE + 1) + x + 1];
      bits += left < right ? "1" : "0";
    }
  }

  let hash = "";
  for (let i = 0; i < bits.length; i += 4) {
    hash += Number.parseInt(bits.slice(i, i + 4), 2).toString(16);
  }

  return { hash, colorFeature };
}

async function convertIcon(sourcePng, targetWebp) {
  await sharp(sourcePng)
    .resize(ICON_SIZE, ICON_SIZE, { fit: "fill" })
    .webp({ quality: 90 })
    .toFile(targetWebp);
}

async function main() {
  await mkdir(skillSourceDir, { recursive: true });
  await mkdir(outSkillsDir, { recursive: true });
  await mkdir(outDataDir, { recursive: true });
  await mkdir(reportDir, { recursive: true });

  const commit = await resolveCommitSha();
  let gameDataVersion = "unknown";
  const versionCache = join(cacheDir, "version");
  try {
    if (!FORCE_REFRESH && (await exists(versionCache))) {
      gameDataVersion = (await readFile(versionCache, "utf8")).trim();
      console.log(`使用缓存：version (${gameDataVersion})`);
    } else {
      gameDataVersion = (await fetchText(`${RAW_BASE}/version`)).trim();
      await writeFile(versionCache, `${gameDataVersion}\n`);
    }
  } catch (error) {
    if (await exists(versionCache)) {
      gameDataVersion = (await readFile(versionCache, "utf8")).trim();
      console.warn(`version 下载失败，回退缓存：${gameDataVersion}`);
    } else {
      throw error;
    }
  }

  const characterTable = await downloadJson("character_table.json");
  const skillTable = await downloadJson("skill_table.json");
  const patchTable = await downloadJson("char_patch_table.json");

  const { retained, excluded, noSkills } = collectOperators(
    characterTable,
    patchTable,
  );

  const missingSkillDefs = [];
  const skillJobs = [];

  for (const operator of retained) {
    for (const skillRef of operator.skills) {
      const skillId = skillRef.skillId;
      if (!skillId) continue;

      const skillDef = skillTable[skillId];
      if (!skillDef) {
        missingSkillDefs.push({
          characterId: operator.characterId,
          name: operator.name,
          skillId,
        });
        continue;
      }

      skillJobs.push({
        characterId: operator.characterId,
        operatorName: operator.name,
        skillId,
        skillName: skillDef.levels?.[0]?.name ?? skillId,
        iconKeys: candidateIconKeys(skillId, skillDef, skillRef),
      });
    }
  }

  const uniqueIconKeys = [
    ...new Set(skillJobs.flatMap((job) => job.iconKeys)),
  ];
  console.log(`准备下载技能图标候选 ${uniqueIconKeys.length} 个…`);

  let downloaded = 0;
  let skipped = 0;
  let failedDownloads = 0;
  await mapPool(uniqueIconKeys, DOWNLOAD_CONCURRENCY, async (iconKey) => {
    const result = await downloadIconIfNeeded(iconKey);
    if (result.ok && result.skipped) skipped += 1;
    else if (result.ok) downloaded += 1;
    else failedDownloads += 1;
    if ((downloaded + skipped + failedDownloads) % 50 === 0) {
      console.log(
        `图标进度：下载 ${downloaded}，复用 ${skipped}，失败 ${failedDownloads}`,
      );
    }
    return result;
  });
  console.log(
    `图标下载结束：下载 ${downloaded}，复用 ${skipped}，失败 ${failedDownloads}`,
  );

  const missingIcons = [];
  const referencedIconFiles = new Set();
  const featureCache = new Map();
  const usedOutputNames = new Set();
  const operatorSkillMap = new Map();

  for (const job of skillJobs) {
    let resolvedKey = null;
    let sourcePath = null;

    for (const key of job.iconKeys) {
      const candidate = join(skillSourceDir, iconFileName(key));
      if (await exists(candidate)) {
        resolvedKey = key;
        sourcePath = candidate;
        break;
      }
    }

    if (!sourcePath || !resolvedKey) {
      missingIcons.push({
        characterId: job.characterId,
        name: job.operatorName,
        skillId: job.skillId,
        skillName: job.skillName,
        tried: job.iconKeys.map(iconFileName),
      });
      continue;
    }

    referencedIconFiles.add(iconFileName(resolvedKey));
    const outputBase = sanitizeFileStem(job.skillId);
    const outputName = `${outputBase}.webp`;
    const outputPath = join(outSkillsDir, outputName);
    usedOutputNames.add(outputName);

    if (!featureCache.has(sourcePath)) {
      await convertIcon(sourcePath, outputPath);
      featureCache.set(sourcePath, await computeFeatures(sourcePath));
    } else if (!(await exists(outputPath))) {
      await convertIcon(sourcePath, outputPath);
    }

    const features = featureCache.get(sourcePath);
    const list = operatorSkillMap.get(job.characterId) || [];
    list.push({
      skillId: job.skillId,
      name: job.skillName,
      icon: `/skills/${outputName}`,
      iconKey: resolvedKey,
      hash: features.hash,
      colorFeature: features.colorFeature,
    });
    operatorSkillMap.set(job.characterId, list);
  }

  const operators = retained.map((operator) => ({
    characterId: operator.characterId,
    name: operator.name,
    profession: operator.profession,
    rarity: operator.rarity,
    isNotObtainable: operator.isNotObtainable,
    appellation: operator.appellation,
    skills: operatorSkillMap.get(operator.characterId) || [],
  }));

  const existingOutputs = await readdir(outSkillsDir);
  for (const name of existingOutputs) {
    if (!name.endsWith(".webp")) continue;
    if (!usedOutputNames.has(name)) {
      await rm(join(outSkillsDir, name), { force: true });
    }
  }

  const cachedIcons = (await readdir(skillSourceDir)).filter(
    (name) => name.startsWith("skill_icon_") && name.endsWith(".png"),
  );
  const unreferencedIcons = cachedIcons.filter(
    (name) => !referencedIconFiles.has(name),
  );

  const nameGroups = new Map();
  for (const operator of operators) {
    const list = nameGroups.get(operator.name) || [];
    list.push(operator.characterId);
    nameGroups.set(operator.name, list);
  }
  const duplicateNames = [...nameGroups.entries()]
    .filter(([, ids]) => ids.length > 1)
    .map(([name, characterIds]) => ({ name, characterIds }));

  const skillCount = operators.reduce(
    (sum, operator) => sum + operator.skills.length,
    0,
  );

  const versionInfo = {
    source: SOURCE,
    commit,
    gameDataVersion,
    generatedAt: new Date().toISOString(),
    operatorCount: operators.length,
    skillCount,
    missingIconCount: missingIcons.length,
    missingSkillDefCount: missingSkillDefs.length,
  };

  await writeFile(
    join(outDataDir, "operators.json"),
    `${JSON.stringify(operators, null, 2)}\n`,
  );
  await writeFile(
    join(outDataDir, "data-version.json"),
    `${JSON.stringify(versionInfo, null, 2)}\n`,
  );

  const operatorsHash = createHash("sha256")
    .update(JSON.stringify(operators))
    .digest("hex");

  const report = {
    ...versionInfo,
    retainedCount: retained.length,
    excludedCount: excluded.length,
    noSkillOperators: noSkills,
    missingSkillDefs,
    missingIcons,
    duplicateNames,
    unreferencedIconCount: unreferencedIcons.length,
    unreferencedIcons: unreferencedIcons.slice(0, 200),
    operatorsSha256: operatorsHash,
    criticalMissing: missingIcons.length + missingSkillDefs.length,
  };

  await writeFile(
    join(reportDir, "arknights-data-report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
  );

  console.log(
    `完成：干员 ${operators.length}，技能 ${skillCount}，缺失图标 ${missingIcons.length}，缺失技能定义 ${missingSkillDefs.length}`,
  );
  console.log("输出：public/data/operators.json");
  console.log("输出：public/data/data-version.json");
  console.log("报告：reports/arknights-data-report.json");

  if (report.criticalMissing > 0) {
    console.error(
      `存在 ${report.criticalMissing} 项关键缺失，请查看 reports/arknights-data-report.json`,
    );
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
