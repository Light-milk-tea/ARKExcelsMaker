<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  disposeOcr,
  initializeOcr,
  subscribeOcrLoadStage,
  type OcrLoadStage,
  recognizeImage,
  type RecognitionResult,
} from "./services/ocr";
import {
  DEFAULT_SKILL_CROP_CONFIG,
  recognizeOperatorSkills,
} from "./services/skillRecognition";
import type {
  OperatorSkillRecognition,
  SkillCropConfig,
  SkillRecognitionResult,
} from "./types/skill";

type Status =
  | "idle"
  | "initializing"
  | "recognizing"
  | "analyzing"
  | "done"
  | "error";

const MAX_FILE_SIZE = 15 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/bmp"]);

const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const previewUrl = ref("");
const status = ref<Status>("idle");
const errorMessage = ref("");
const result = ref<RecognitionResult | null>(null);
const skillResult = ref<SkillRecognitionResult | null>(null);
const cropConfig = ref<SkillCropConfig>({ ...DEFAULT_SKILL_CROP_CONFIG });
const showSkillDebug = ref(false);
const skillOverrides = ref<Record<number, number>>({});
const isDragging = ref(false);
const copied = ref(false);
const loadStage = ref<OcrLoadStage>("models");
let unsubscribeLoadStage: (() => void) | null = null;

const isBusy = computed(
  () =>
    status.value === "initializing" ||
    status.value === "recognizing" ||
    status.value === "analyzing",
);

const statusText = computed(() => {
  switch (status.value) {
    case "initializing": {
      if (loadStage.value === "models") {
        return "正在下载 OCR 模型（约 20 MB），网络较慢时请耐心等待…";
      }
      if (loadStage.value === "runtime") {
        return "正在下载推理运行时 WASM，首次使用可能需要较长时间…";
      }
      return "正在初始化检测模型…";
    }
    case "recognizing":
      return "正在识别图片中的文字…";
    case "analyzing":
      return "正在定位干员并比较技能图标…";
    case "done":
      return skillResult.value?.items.length
        ? `识别完成，找到 ${skillResult.value.items.length} 名干员`
        : result.value?.text
          ? "文字识别完成，未匹配到干员技能"
          : "识别完成，未发现文字";
    case "error":
      return errorMessage.value;
    default:
      return selectedFile.value ? "图片已就绪" : "请选择一张图片";
  }
});

function openFilePicker() {
  if (!isBusy.value) {
    fileInput.value?.click();
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) {
    selectFile(file);
  }
  input.value = "";
}

function onDrop(event: DragEvent) {
  isDragging.value = false;
  if (isBusy.value) return;

  const file = event.dataTransfer?.files[0];
  if (file) {
    selectFile(file);
  }
}

function selectFile(file: File) {
  errorMessage.value = "";
  result.value = null;
  skillResult.value = null;
  skillOverrides.value = {};
  copied.value = false;

  if (!ALLOWED_TYPES.has(file.type)) {
    setError("请选择 PNG、JPG、WEBP 或 BMP 格式的图片。");
    return;
  }

  if (file.size > MAX_FILE_SIZE) {
    setError("图片不能超过 15 MB，请压缩后重试。");
    return;
  }

  revokePreview();
  selectedFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  status.value = "idle";
}

async function runRecognition() {
  const file = selectedFile.value;
  if (!file || isBusy.value) return;

  errorMessage.value = "";
  result.value = null;
  copied.value = false;

  try {
    status.value = "initializing";
    await initializeOcr();
    status.value = "recognizing";
    result.value = await recognizeImage(file);
    status.value = "analyzing";
    skillResult.value = await recognizeOperatorSkills(
      file,
      result.value.lines,
      cropConfig.value,
    );
    status.value = "done";
  } catch (error) {
    setError(error instanceof Error ? error.message : "识别失败，请重试。");
  }
}

async function rerunSkillRecognition() {
  if (!selectedFile.value || !result.value || isBusy.value) return;

  try {
    status.value = "analyzing";
    skillOverrides.value = {};
    skillResult.value = await recognizeOperatorSkills(
      selectedFile.value,
      result.value.lines,
      cropConfig.value,
    );
    status.value = "done";
  } catch (error) {
    setError(error instanceof Error ? error.message : "技能识别失败，请重试。");
  }
}

async function copyResult() {
  if (!result.value?.text) return;

  try {
    await navigator.clipboard.writeText(result.value.text);
    copied.value = true;
    window.setTimeout(() => {
      copied.value = false;
    }, 1800);
  } catch {
    setError("复制失败，请手动选择识别结果。");
  }
}

function clearSelection() {
  if (isBusy.value) return;
  revokePreview();
  selectedFile.value = null;
  result.value = null;
  skillResult.value = null;
  skillOverrides.value = {};
  errorMessage.value = "";
  status.value = "idle";
}

function setError(message: string) {
  errorMessage.value = message;
  status.value = "error";
}

function revokePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = "";
  }
}

function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(0)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function selectedCandidate(item: OperatorSkillRecognition, index: number) {
  return item.candidates[skillOverrides.value[index] ?? 0] ?? item.best;
}

function selectCandidate(itemIndex: number, candidateIndex: number) {
  skillOverrides.value = {
    ...skillOverrides.value,
    [itemIndex]: candidateIndex,
  };
}

function skillStatusText(item: OperatorSkillRecognition) {
  switch (item.status) {
    case "matched":
      return "高可信匹配";
    case "ambiguous":
      return "存在相近候选";
    case "low-confidence":
      return "图标可信度较低";
    case "name-uncertain":
      return "干员名字不确定";
    case "out-of-bounds":
      return "图标区域超出图片";
    case "no-skills":
      return "没有可匹配技能";
  }
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function skillIconUrl(path: string) {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, "")}`.replace(
    /\/{2,}/g,
    "/",
  );
}

onMounted(() => {
  unsubscribeLoadStage = subscribeOcrLoadStage((stage) => {
    loadStage.value = stage;
  });
});

onBeforeUnmount(() => {
  unsubscribeLoadStage?.();
  unsubscribeLoadStage = null;
  revokePreview();
  void disposeOcr();
});
</script>

<template>
  <main class="page-shell">
    <header class="hero">
      <span class="eyebrow">PaddleOCR · 浏览器本地运行</span>
      <h1>图片文字识别</h1>
      <p>上传图片即可提取文字。图片不会上传到服务器，识别过程在你的设备上完成。</p>
    </header>

    <section class="workspace" aria-label="图片文字识别工具">
      <div class="input-panel">
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".png,.jpg,.jpeg,.webp,.bmp,image/png,image/jpeg,image/webp,image/bmp"
          @change="onFileChange"
        />

        <button
          v-if="!selectedFile"
          class="drop-zone"
          :class="{ dragging: isDragging }"
          type="button"
          :disabled="isBusy"
          @click="openFilePicker"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="onDrop"
        >
          <span class="upload-icon" aria-hidden="true">↑</span>
          <strong>点击选择或拖放图片</strong>
          <small>支持 PNG、JPG、WEBP、BMP，最大 15 MB</small>
        </button>

        <div v-else class="preview-card">
          <div class="preview-frame">
            <img :src="previewUrl" :alt="`待识别图片：${selectedFile.name}`" />
            <svg
              v-if="skillResult"
              class="detection-overlay"
              :viewBox="`0 0 ${skillResult.image.width} ${skillResult.image.height}`"
              preserveAspectRatio="xMidYMid meet"
              aria-label="干员名字和技能图标定位框"
            >
              <g
                v-for="(item, index) in skillResult.items"
                :key="`${item.matchedName}-${index}`"
              >
                <rect
                  class="name-detection-box"
                  :x="item.nameBox.x"
                  :y="item.nameBox.y"
                  :width="item.nameBox.width"
                  :height="item.nameBox.height"
                />
                <rect
                  v-if="item.cropRect"
                  class="skill-detection-box"
                  :x="item.cropRect.x"
                  :y="item.cropRect.y"
                  :width="item.cropRect.width"
                  :height="item.cropRect.height"
                />
              </g>
            </svg>
          </div>
          <div class="file-info">
            <div>
              <strong>{{ selectedFile.name }}</strong>
              <span>{{ formatSize(selectedFile.size) }}</span>
            </div>
            <button class="text-button" type="button" :disabled="isBusy" @click="clearSelection">
              重新选择
            </button>
          </div>
        </div>

        <div class="action-row">
          <button
            class="primary-button"
            type="button"
            :disabled="!selectedFile || isBusy"
            @click="runRecognition"
          >
            <span v-if="isBusy" class="spinner" aria-hidden="true"></span>
            {{ isBusy ? "处理中" : "开始识别" }}
          </button>
          <span class="status" :class="{ error: status === 'error' }" role="status">
            {{ statusText }}
          </span>
        </div>
      </div>

      <div class="result-panel">
        <div class="result-heading">
          <div>
            <span class="section-label">识别结果</span>
            <h2>{{ result?.text ? `${result.lines.length} 行文字` : "等待识别" }}</h2>
          </div>
          <button
            v-if="result?.text"
            class="secondary-button"
            type="button"
            @click="copyResult"
          >
            {{ copied ? "已复制" : "复制全文" }}
          </button>
        </div>

        <textarea
          v-if="result?.text"
          class="result-text"
          :value="result.text"
          readonly
          aria-label="识别到的文字"
        ></textarea>
        <div v-else class="empty-result">
          <span aria-hidden="true">文</span>
          <p>识别到的文字将显示在这里</p>
        </div>

        <div v-if="result" class="metrics">
          <span>耗时 {{ Math.round(result.elapsedMs) }} ms</span>
          <span>{{ result.image.width }} × {{ result.image.height }}</span>
          <span>后端 {{ result.provider }}</span>
        </div>

        <details v-if="result?.lines.length" class="line-details">
          <summary>查看逐行置信度</summary>
          <ol>
            <li v-for="(line, index) in result.lines" :key="`${index}-${line.text}`">
              <span>{{ line.text }}</span>
              <b>{{ (line.score * 100).toFixed(1) }}%</b>
            </li>
          </ol>
        </details>
      </div>
    </section>

    <section v-if="skillResult" class="skill-results" aria-label="干员技能识别结果">
      <div class="skill-results-heading">
        <div>
          <span class="section-label">技能图标匹配</span>
          <h2>
            {{
              skillResult.items.length
                ? `找到 ${skillResult.items.length} 名干员`
                : "未匹配到干员"
            }}
          </h2>
        </div>
        <button
          class="secondary-button"
          type="button"
          @click="showSkillDebug = !showSkillDebug"
        >
          {{ showSkillDebug ? "收起校准" : "校准裁剪区域" }}
        </button>
      </div>

      <div v-if="showSkillDebug" class="crop-debug-panel">
        <label>
          <span>图标大小：{{ cropConfig.iconSizeByTextHeight.toFixed(1) }}× 文字高度</span>
          <input
            v-model.number="cropConfig.iconSizeByTextHeight"
            type="range"
            min="1.2"
            max="6"
            step="0.1"
          />
        </label>
        <label>
          <span>垂直间距：{{ cropConfig.verticalGapByTextHeight.toFixed(1) }}×</span>
          <input
            v-model.number="cropConfig.verticalGapByTextHeight"
            type="range"
            min="-1"
            max="4"
            step="0.1"
          />
        </label>
        <label>
          <span>水平偏移：{{ cropConfig.horizontalOffsetByTextHeight.toFixed(1) }}×</span>
          <input
            v-model.number="cropConfig.horizontalOffsetByTextHeight"
            type="range"
            min="-3"
            max="3"
            step="0.1"
          />
        </label>
        <label>
          <span>外扩边距：{{ percent(cropConfig.paddingRatio) }}</span>
          <input
            v-model.number="cropConfig.paddingRatio"
            type="range"
            min="0"
            max="0.3"
            step="0.01"
          />
        </label>
        <button
          class="primary-button"
          type="button"
          :disabled="isBusy"
          @click="rerunSkillRecognition"
        >
          应用并重新匹配
        </button>
        <p>预览图中绿色框是干员名字，橙色框是推算出的技能图标区域。</p>
      </div>

      <div v-if="skillResult.items.length" class="skill-card-grid">
        <article
          v-for="(item, itemIndex) in skillResult.items"
          :key="`${item.matchedName}-${item.nameBox.x}-${item.nameBox.y}`"
          class="skill-card"
          :class="{ uncertain: item.status !== 'matched' }"
        >
          <header>
            <div>
              <strong>{{ item.matchedName }}</strong>
              <span v-if="item.rawText !== item.matchedName">
                OCR：{{ item.rawText }}
              </span>
            </div>
            <b>{{ skillStatusText(item) }}</b>
          </header>

          <div v-if="item.cropDataUrl" class="skill-comparison">
            <figure>
              <img :src="item.cropDataUrl" alt="从截图裁剪的技能图标" />
              <figcaption>截图裁剪</figcaption>
            </figure>
            <span aria-hidden="true">→</span>
            <figure v-if="selectedCandidate(item, itemIndex)">
              <img
                :src="skillIconUrl(selectedCandidate(item, itemIndex)!.skill.icon)"
                :alt="selectedCandidate(item, itemIndex)!.skill.name"
              />
              <figcaption>{{ selectedCandidate(item, itemIndex)!.skill.name }}</figcaption>
            </figure>
          </div>

          <div v-if="selectedCandidate(item, itemIndex)" class="skill-score">
            <span>综合 {{ percent(selectedCandidate(item, itemIndex)!.score) }}</span>
            <span>边缘 {{ percent(selectedCandidate(item, itemIndex)!.edgeSimilarity) }}</span>
            <span>灰度 {{ percent(selectedCandidate(item, itemIndex)!.pixelSimilarity) }}</span>
            <span>颜色 {{ percent(selectedCandidate(item, itemIndex)!.colorSimilarity) }}</span>
          </div>

          <div v-if="item.candidates.length > 1" class="candidate-list">
            <span>候选技能（可手动更正）</span>
            <button
              v-for="(candidate, candidateIndex) in item.candidates"
              :key="candidate.skill.skillId"
              type="button"
              :class="{ selected: (skillOverrides[itemIndex] ?? 0) === candidateIndex }"
              @click="selectCandidate(itemIndex, candidateIndex)"
            >
              <img
                :src="skillIconUrl(candidate.skill.icon)"
                :alt="candidate.skill.name"
              />
              <span>{{ candidate.skill.name }}</span>
              <b>{{ percent(candidate.score) }}</b>
            </button>
          </div>

          <p v-if="!item.cropDataUrl" class="skill-warning">
            无法从当前名字坐标裁剪技能图标，请打开校准面板调整位置。
          </p>
        </article>
      </div>
      <div v-else class="no-operator-result">
        OCR 结果中没有匹配到干员名字。可检查截图清晰度和干员名单数据。
      </div>
    </section>

    <footer>首次打开时，浏览器需要读取本地模型文件；之后会由浏览器缓存。</footer>
  </main>
</template>
