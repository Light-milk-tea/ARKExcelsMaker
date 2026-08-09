<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { recognizeImage, subscribeOcrProgress } from './services/ocr'
import { matchOperatorName } from './utils/similarity'
import { recognizeOperatorSkills } from './services/skillRecognition'
import type { SkillRecognitionResult, SkillRecognitionStatus } from './types/skill'

interface OperatorSkill {
  name: string
  icon: string
  skillId?: string
}

interface Operator {
  name: string
  profession: string
  rarity: number
  avatar_url?: string
  skills: OperatorSkill[]
}

// data/operators.json 的原始格式
interface RawOperatorData {
  characterId: string
  name: string
  profession: string
  rarity: number | null
  isNotObtainable: boolean
  appellation: string | null
  skills: Array<{
    skillId: string
    name: string
    icon: string
    iconKey: string
    hash: string
    colorFeature: [number, number, number]
  }>
}

const RARITIES = ['1星', '2星', '3星', '4星', '5星', '6星'] as const
const PROFESSIONS = ['先锋', '近卫', '重装', '狙击', '术师', '医疗', '辅助', '特种'] as const

const allOperators = ref<Record<string, Operator[]>>({})
const loading = ref(true)
const loadError = ref('')
const recognizing = ref(false)
const ocrProgress = reactive<{ stage: string; percent: number }>({ stage: '', percent: 0 })
const recognizingElapsed = ref(0)
const ocrUsed = ref(false)
let recognizeTimer: ReturnType<typeof setInterval> | null = null
let currentNotification: HTMLElement | null = null
const pasteTarget = ref<HTMLTextAreaElement>()
const fileInput = ref<HTMLInputElement>()
const skillDisplayMode = ref<0 | 1>(0)
const skillResult = ref<SkillRecognitionResult | null>(null)
const cropPreviewOpen = ref(false)

const selectedStars = reactive(new Set<string>(JSON.parse(localStorage.getItem('operatorFilter_stars') || '[]')))
const selectedClasses = reactive(new Set<string>(JSON.parse(localStorage.getItem('operatorFilter_classes') || '[]')))
const selectedOperators = reactive(new Set<string>())
const selectedSkills = reactive(new Set<string>())
const ocrPriority = ref<string[]>([])
const e1Mode = ref(localStorage.getItem('operatorFilter_e1Mode') === 'true')
const lowGapOperators = reactive(new Set<string>())

const STATUS_LABELS: Record<SkillRecognitionStatus, string> = {
  matched: '已匹配',
  'low-confidence': '低置信',
  'low-gap': '分差过小',
  ambiguous: '候选接近',
  'name-uncertain': '名字不确定',
  'out-of-bounds': '裁剪越界',
  'no-skills': '无技能',
}

const cropPreviewItems = computed(() => skillResult.value?.items ?? [])
const hasCropPreview = computed(() => cropPreviewItems.value.length > 0)

watch(e1Mode, (val) => {
  localStorage.setItem('operatorFilter_e1Mode', String(val))
  if (val) {
    const toSwitch: string[] = []
    selectedSkills.forEach(skillKey => {
      const [opName, skillName] = skillKey.split('::')
      const op = findOperatorByName(opName)
      if (op) {
        const visibleSkills = getVisibleSkills(op)
        if (!visibleSkills.includes(skillName) && visibleSkills.length >= 2) {
          toSwitch.push(opName)
        }
      }
    })
    toSwitch.forEach(opName => {
      const op = findOperatorByName(opName)
      if (op) {
        selectedSkills.delete(opName + '::' + op.skills[2])
        selectedSkills.add(opName + '::' + op.skills[1])
      }
    })
  }
})

function getVisibleSkills(op: Operator): OperatorSkill[] {
  return e1Mode.value ? op.skills.slice(0, 2) : op.skills
}

const totalCount = computed(() => {
  let count = 0
  RARITIES.forEach(r => {
    const ops = allOperators.value[r]
    if (ops) count += ops.length
  })
  return count
})

const displayCount = computed(() => {
  let count = 0
  RARITIES.forEach(r => {
    const ops = allOperators.value[r]
    if (!ops) return
    const starMatch = selectedStars.size === 0 || selectedStars.has(r)
    if (!starMatch) return
    ops.forEach(op => {
      const classMatch = selectedClasses.size === 0 || selectedClasses.has(op.profession)
      if (classMatch) count++
    })
  })
  return count
})

const selectedInfo = computed(() => {
  if (selectedOperators.size > 0) return `已选 ${selectedOperators.size} 干员`
  return ''
})

const filteredOperators = computed(() => {
  const result: { rarity: string; op: Operator }[] = []
  RARITIES.forEach(r => {
    const ops = allOperators.value[r]
    if (!ops) return
    const starMatch = selectedStars.size === 0 || selectedStars.has(r)
    if (!starMatch) return
    ops.forEach(op => {
      const classMatch = selectedClasses.size === 0 || selectedClasses.has(op.profession)
      if (classMatch) result.push({ rarity: r, op })
    })
  })
  if (ocrPriority.value.length > 0) {
    result.sort((a, b) => {
      const ai = ocrPriority.value.indexOf(a.op.name)
      const bi = ocrPriority.value.indexOf(b.op.name)
      const aIdx = ai === -1 ? Infinity : ai
      const bIdx = bi === -1 ? Infinity : bi
      return aIdx - bIdx
    })
  }
  return result
})

function getRarityNum(rarity: string): number {
  return parseInt(rarity)
}

function getFirstChar(name: string): string {
  return name.charAt(0)
}

function assetUrl(path: string): string {
  return `${import.meta.env.BASE_URL}${path}`.replace(/\/{2,}/g, '/')
}

function getAvatarUrl(avatarUrl?: string): string {
  if (!avatarUrl) return ''
  return assetUrl('wiki_upload/images/' + avatarUrl.replace(/^\/+/, ''))
}

function getSkillIconUrl(skill: OperatorSkill): string {
  // 技能图标使用 data 中的路径
  return assetUrl(skill.icon.replace(/^\/+/, ''))
}

function getLibrarySkillIconUrl(icon: string): string {
  return assetUrl(icon.replace(/^\/+/, ''))
}

function getSkillStatusLabel(status: SkillRecognitionStatus): string {
  return STATUS_LABELS[status] || status
}

function formatScore(score: number | undefined): string {
  if (score == null || Number.isNaN(score)) return '-'
  return (score * 100).toFixed(1) + '%'
}

function toggleCropPreview() {
  cropPreviewOpen.value = !cropPreviewOpen.value
}

function saveFilters() {
  localStorage.setItem('operatorFilter_stars', JSON.stringify(Array.from(selectedStars)))
  localStorage.setItem('operatorFilter_classes', JSON.stringify(Array.from(selectedClasses)))
}

function toggleStar(r: string) {
  if (selectedStars.has(r)) selectedStars.delete(r)
  else selectedStars.add(r)
  saveFilters()
}

function toggleClass(p: string) {
  if (selectedClasses.has(p)) selectedClasses.delete(p)
  else selectedClasses.add(p)
  saveFilters()
}

function toggleOperator(op: Operator) {
  const visibleSkills = getVisibleSkills(op)
  if (selectedOperators.has(op.name)) {
    selectedOperators.delete(op.name)
    visibleSkills.forEach((skill) => {
      selectedSkills.delete(op.name + '::' + skill.name)
    })
  } else {
    selectedOperators.add(op.name)
    if (visibleSkills.length > 0) {
      visibleSkills.forEach((skill) => {
        selectedSkills.delete(op.name + '::' + skill.name)
      })
      selectedSkills.add(op.name + '::' + visibleSkills[visibleSkills.length - 1].name)
    }
  }
}

function toggleSkill(opName: string, skillKey: string) {
  // 手动点击技能后，移除低可信度标记
  lowGapOperators.delete(opName)

  if (selectedSkills.has(skillKey)) {
    selectedOperators.delete(opName)
    const op = findOperatorByName(opName)
    if (op) {
      op.skills.forEach((skill) => {
        selectedSkills.delete(opName + '::' + skill.name)
      })
    }
    return
  }
  if (!selectedOperators.has(opName)) {
    selectedOperators.add(opName)
  }
  const op = findOperatorByName(opName)
  if (op) {
    op.skills.forEach((skill) => {
      selectedSkills.delete(opName + '::' + skill.name)
    })
  }
  selectedSkills.add(skillKey)
}

function findOperatorByName(name: string): Operator | undefined {
  for (const rarity of RARITIES) {
    const ops = allOperators.value[rarity]
    if (ops) {
      const found = ops.find(op => op.name === name)
      if (found) return found
    }
  }
  return undefined
}

function isSelected(name: string) {
  return selectedOperators.has(name)
}

function isSkillSelected(skillKey: string) {
  return selectedSkills.has(skillKey)
}

function notify(message: string, type: 'success' | 'warning' | 'error' | 'info' = 'info') {
  const container = document.createElement('div')
  container.style.position = 'fixed'
  container.style.top = '16px'
  container.style.left = '50%'
  container.style.transform = 'translateX(-50%)'
  container.style.zIndex = '9999'
  container.style.padding = '10px 14px'
  container.style.borderRadius = '6px'
  container.style.color = '#fff'
  container.style.background = type === 'error' ? '#d9534f' : type === 'warning' ? '#f0ad4e' : type === 'success' ? '#28a745' : '#2f6fed'
  container.style.boxShadow = '0 8px 20px rgba(0, 0, 0, 0.2)'
  container.style.fontSize = '13px'
  container.textContent = message
  document.body.appendChild(container)
  window.setTimeout(() => {
    container.remove()
  }, 2200)
}

function notifyNotification(message: string, title: string, type: 'success' | 'warning' | 'error' | 'info' = 'info', autoClose = true) {
  const container = document.createElement('div')
  container.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    min-width: 320px;
    max-width: 420px;
    padding: 16px;
    border-radius: 8px;
    background: #1e2a45;
    border: 1px solid #334466;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    animation: slideIn 0.3s ease-out;
    font-family: inherit;
  `

  const colors = {
    error: { border: '#d9534f', icon: '✕', iconColor: '#d9534f', messageColor: '#f5b7b1' },
    warning: { border: '#e6a23c', icon: '⚠', iconColor: '#e6a23c', messageColor: '#f5d79e' },
    success: { border: '#67c23a', icon: '✓', iconColor: '#67c23a', messageColor: '#a0a0a0' },
    info: { border: '#409eff', icon: 'ℹ', iconColor: '#409eff', messageColor: '#a0a0a0' }
  }

  const color = colors[type]
  container.style.borderLeft = `4px solid ${color.border}`

  container.innerHTML = `
    <div style="display: flex; align-items: flex-start; gap: 12px;">
      <span style="font-size: 18px; color: ${color.iconColor}; flex-shrink: 0;">${color.icon}</span>
      <div style="flex: 1; min-width: 0;">
        <div style="font-size: 14px; font-weight: 600; color: #e0e0e0; margin-bottom: 4px;">${title}</div>
        <div style="font-size: 13px; color: ${color.messageColor}; line-height: 1.5; word-break: break-word;">${message}</div>
      </div>
      <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: #666; cursor: pointer; font-size: 16px; padding: 0; line-height: 1;">✕</button>
    </div>
  `

  document.body.appendChild(container)
  currentNotification = container

  if (!document.getElementById('notification-styles')) {
    const style = document.createElement('style')
    style.id = 'notification-styles'
    style.textContent = `
      @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
      }
    `
    document.head.appendChild(style)
  }

  if (autoClose) {
    window.setTimeout(() => {
      container.style.animation = 'slideOut 0.3s ease-in forwards'
      window.setTimeout(() => container.remove(), 300)
    }, 4000)
  }
}

function isStarActive(r: string) {
  return selectedStars.has(r)
}

function isClassActive(p: string) {
  return selectedClasses.has(p)
}

function resolveOperatorsFromOcrLines(lines: Array<{ text: string; score?: number }>) {
  const selections: Array<{ rawText: string; matchedName: string; confidence: number }> = []
  const seen = new Set<string>()
  const allOperatorData = Object.values(allOperators.value).flatMap((ops) => ops)

  lines.forEach((line) => {
    const trimmed = line.text?.trim()
    if (!trimmed) return

    const nameMatch = matchOperatorName(trimmed, allOperatorData)
    if (!nameMatch.name || nameMatch.confidence < 0.64 || nameMatch.operators.length === 0) return

    if (seen.has(nameMatch.name)) return
    seen.add(nameMatch.name)

    selections.push({
      rawText: trimmed,
      matchedName: nameMatch.name,
      confidence: nameMatch.confidence,
    })
  })

  return selections
}

function applySkillRecognitionSelections(ocrSelections: Array<{ matchedName: string }>) {
  selectedOperators.clear()
  selectedSkills.clear()
  lowGapOperators.clear()

  const skillItems = skillResult.value?.items ?? []
  const selectedSkillByOperator = new Map<string, string>()

  skillItems.forEach((item, itemIndex) => {
    if (!item.matchedName) return
    const selection = ocrSelections.find((entry) => entry.matchedName === item.matchedName)
    if (!selection) return

    const chosenCandidate = item.best
    if (!chosenCandidate?.skill.name) return

    selectedSkillByOperator.set(item.matchedName, chosenCandidate.skill.name)

    // 检测 low-gap 状态，使用 op.name（可能带有职业标识）
    if (item.status === 'low-gap') {
      const op = findOperatorByName(item.matchedName)
      if (op) {
        lowGapOperators.add(op.name)
      }
    }
  })

  ocrSelections.forEach((selection) => {
    const op = findOperatorByName(selection.matchedName)
    if (!op) return

    selectedOperators.add(op.name)
    const visibleSkills = getVisibleSkills(op)
    visibleSkills.forEach((skill) => {
      selectedSkills.delete(op.name + '::' + skill.name)
    })

    const resolvedSkillName = selectedSkillByOperator.get(selection.matchedName)
    if (resolvedSkillName) {
      selectedSkills.add(op.name + '::' + resolvedSkillName)
    } else if (visibleSkills.length > 0) {
      selectedSkills.add(op.name + '::' + visibleSkills[visibleSkills.length - 1].name)
    }
  })
}

async function handleGenerate() {
  const parts: string[] = []
  selectedSkills.forEach((skillKey) => {
    const [opName, skillName] = skillKey.split('::')
    const op = findOperatorByName(opName)
    if (op && skillName) {
      const idx = op.skills.findIndex((skill) => skill.name === skillName) + 1
      if (idx > 0) {
        parts.push(opName + idx)
      }
    }
  })
  selectedOperators.forEach((opName) => {
    const hasSkill = Array.from(selectedSkills).some((key) => key.startsWith(opName + '::'))
    if (!hasSkill) {
      parts.push(opName)
    }
  })
  if (parts.length === 0) return
  const text = parts.join('+')
  try {
    await navigator.clipboard.writeText(text)
    notify('已复制到剪贴板：' + text, 'success')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    notify('已复制到剪贴板：' + text, 'success')
  }
}

function clearStars() {
  selectedStars.clear()
  saveFilters()
}

function clearClasses() {
  selectedClasses.clear()
  saveFilters()
}

function triggerPaste() {
  pasteTarget.value?.focus()
}

function triggerUpload() {
  fileInput.value?.click()
}

function handleFileUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  processImage(file)
}

async function processImage(file: File) {
  recognizing.value = true
  recognizingElapsed.value = 0
  recognizeTimer = setInterval(() => recognizingElapsed.value++, 1000)
  ocrProgress.stage = ''
  ocrProgress.percent = 0
  lowGapOperators.clear()
  cropPreviewOpen.value = false
  skillResult.value = null
  if (currentNotification) { currentNotification.remove(); currentNotification = null }
  notify('正在识别文字...', 'info')

  try {
    selectedOperators.clear()
    selectedSkills.clear()

    const res = await recognizeImage(file)
    skillResult.value = await recognizeOperatorSkills(file, res.lines)

    const ocrSelections = resolveOperatorsFromOcrLines(res.lines)

    if (ocrSelections.length === 0) {
      notify('未识别到干员，请确认截图中有干员名字', 'warning')
      return
    }

    ocrPriority.value = ocrSelections.map((selection) => selection.matchedName)
    applySkillRecognitionSelections(ocrSelections)

    ocrUsed.value = true
    notify('已识别 ' + ocrSelections.length + ' 个干员：' + ocrSelections.map((selection) => selection.matchedName).join('、'), 'success')

    // 显示 low-gap 警告提示
    if (lowGapOperators.size > 0) {
      const operatorNames = Array.from(lowGapOperators).join('、')
      notifyNotification(`${operatorNames}技能识别可信度较低，请注意查验`, '低可信度警告', 'warning', false)
    }
  } catch (err: any) {
    notify('识别失败：' + (err.message || '未知错误'), 'error')
  } finally {
    if (recognizeTimer) { clearInterval(recognizeTimer); recognizeTimer = null }
    recognizing.value = false
  }
}

async function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  let file: File | null = null
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      file = item.getAsFile()
      break
    }
  }
  if (!file) return
  e.preventDefault()
  processImage(file)
}

function resetSelection() {
  selectedOperators.clear()
  selectedSkills.clear()
  lowGapOperators.clear()
}

function handleImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
  const placeholder = img.parentElement?.querySelector('.avatar-placeholder') as HTMLElement
  if (placeholder) placeholder.style.display = 'flex'
}

onMounted(async () => {
  const unsubProgress = subscribeOcrProgress((p) => {
    ocrProgress.stage = p.stage
    ocrProgress.percent = p.percent
  })

  try {
    const res = await fetch(assetUrl('data/operators.json'))
    if (!res.ok) throw new Error('加载失败: ' + res.status)
    const rawData = (await res.json()) as RawOperatorData[]

    const grouped: Record<string, Operator[]> = {}
    RARITIES.forEach((rarity) => {
      grouped[rarity] = []
    })

    // 处理职业名称映射
    const PROFESSION_MAP: Record<string, string> = {
      WARRIOR: '近卫',
      TANK: '重装',
      SNIPER: '狙击',
      CASTER: '术师',
      MEDIC: '医疗',
      SUPPORT: '辅助',
      SPECIAL: '特种',
      PIONEER: '先锋',
    }

    // 统计每个名字出现的职业，用于判断是否有多种形态
    const nameProfessions = new Map<string, Set<string>>()
    rawData.forEach((item) => {
      if (item.isNotObtainable) return
      if (!nameProfessions.has(item.name)) {
        nameProfessions.set(item.name, new Set())
      }
      nameProfessions.get(item.name)!.add(item.profession)
    })

    rawData.forEach((item) => {
      // 过滤掉不可获取的干员
      if (item.isNotObtainable) return

      // rarity 是 0-5，实际星级是 rarity + 1
      const rarityNum = (item.rarity ?? 0) + 1
      const rarityKey = `${rarityNum}星`
      if (!RARITIES.includes(rarityKey as any)) return

      // 对于有多种形态的干员，给非默认形态加上职业标识
      const professions = nameProfessions.get(item.name)
      let displayName = item.name
      if (professions && professions.size > 1 && item.profession !== 'CASTER') {
        const professionName = PROFESSION_MAP[item.profession] || item.profession
        displayName = `${item.name}(${professionName})`
      }

      const normalized: Operator = {
        name: displayName,
        profession: PROFESSION_MAP[item.profession] || item.profession,
        rarity: rarityNum,
        // 头像路径：wiki_upload/images/{星级}/{干员名}.png
        avatar_url: `${rarityNum}星/${item.name}.png`,
        skills: (item.skills || []).map((skill) => ({
          name: skill.name,
          icon: skill.icon,
          skillId: skill.skillId,
        })),
      }

      if (grouped[rarityKey]) {
        grouped[rarityKey].push(normalized)
      }
    })

    allOperators.value = grouped
  } catch (err: any) {
    loadError.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="operators-page">
    <div class="filter-bar">
      <div class="filter-left">
        <div class="filter-row">
          <span class="filter-label">星级</span>
          <div class="filter-group">
            <button v-for="(r, i) in RARITIES" :key="r" class="filter-btn" :class="['star-' + (i + 1), { active: isStarActive(r) }]" @click="toggleStar(r)">
              {{ i + 1 }}★
            </button>
            <button class="filter-btn" :class="{ active: selectedStars.size === 0 }" @click="clearStars" title="不限星级">不限</button>
          </div>
        </div>
        <div class="filter-row">
          <span class="filter-label">职业</span>
          <div class="filter-group">
            <button v-for="p in PROFESSIONS" :key="p" class="filter-btn" :class="{ active: isClassActive(p) }" @click="toggleClass(p)">
              {{ p }}
            </button>
            <button class="filter-btn" :class="{ active: selectedClasses.size === 0 }" @click="clearClasses" title="不限职业">不限</button>
          </div>
        </div>
      </div>
      <div class="filter-right">
        <div class="filter-row">
          <template v-if="ocrProgress.stage">
            <div class="download-progress-wrap">
              <div class="download-progress-text">{{ ocrProgress.stage }}</div>
              <div class="download-progress-bar"><div class="download-progress-fill" :style="{ width: ocrProgress.percent + '%' }"></div></div>
              <div class="download-progress-time" v-if="recognizingElapsed > 0">已用时 {{ recognizingElapsed }}s</div>
            </div>
          </template>
          <template v-else-if="recognizing">
            <div class="download-progress-wrap">
              <div class="download-progress-text">正在识别中...</div>
              <div class="download-progress-time" v-if="recognizingElapsed > 0">已用时 {{ recognizingElapsed }}s</div>
            </div>
          </template>
          <template v-else-if="!ocrUsed">
            <span class="download-hint">初次使用需要下载识图库，可能需要一定时间</span>
          </template>
          <button class="mode-toggle-btn" :class="{ active: e1Mode }" @click="e1Mode = !e1Mode">{{ e1Mode ? '精一模式' : '精二模式' }}</button>
          <button class="mode-toggle-btn" :class="{ active: skillDisplayMode === 1 }" @click="skillDisplayMode = skillDisplayMode === 0 ? 1 : 0">{{ skillDisplayMode === 0 ? '☰ 文字' : '▣ 图标' }}</button>
        </div>
        <div class="filter-row">
          <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="handleFileUpload" />
          <div class="paste-group">
            <button class="upload-btn" @click="triggerUpload" :disabled="recognizing" title="上传图片">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </button>
            <textarea ref="pasteTarget" class="paste-input" :placeholder="recognizing ? '识别中...' : '粘贴图片进行识别'" :disabled="recognizing" @paste="handlePaste" readonly></textarea>
          </div>
          <button class="reset-selection-btn" @click="resetSelection" :disabled="selectedOperators.size === 0">重置选中</button>
          <button class="generate-btn" @click="handleGenerate" :disabled="selectedOperators.size === 0">生成</button>
        </div>
      </div>
    </div>

    <div class="stats-bar">
      <span>显示: <span class="count">{{ displayCount }}</span> / {{ totalCount }} 干员</span>
      <span class="selected-info" v-if="selectedInfo">{{ selectedInfo }}</span>
    </div>

    <div v-if="hasCropPreview" class="crop-preview-panel">
      <button type="button" class="crop-preview-toggle" @click="toggleCropPreview">
        <span class="crop-preview-chevron" :class="{ open: cropPreviewOpen }">▸</span>
        <span>技能裁剪预览</span>
        <span class="crop-preview-count">{{ cropPreviewItems.length }}</span>
      </button>
      <div v-if="cropPreviewOpen" class="crop-preview-body">
        <div class="crop-preview-grid">
          <div
            v-for="(item, index) in cropPreviewItems"
            :key="`${item.matchedName}-${index}`"
            class="crop-preview-card"
            :class="'status-' + item.status"
          >
            <div class="crop-preview-images">
              <div class="crop-preview-thumb">
                <img v-if="item.cropDataUrl" :src="item.cropDataUrl" :alt="(item.matchedName || '裁剪') + ' 裁剪'" />
                <div v-else class="crop-preview-empty">无裁剪</div>
                <span class="crop-preview-caption">裁剪</span>
              </div>
              <div class="crop-preview-thumb">
                <img
                  v-if="item.best?.skill.icon"
                  :src="getLibrarySkillIconUrl(item.best.skill.icon)"
                  :alt="item.best.skill.name"
                />
                <div v-else class="crop-preview-empty">无匹配</div>
                <span class="crop-preview-caption">匹配</span>
              </div>
            </div>
            <div class="crop-preview-meta">
              <div class="crop-preview-name" :title="item.matchedName || item.rawText">{{ item.matchedName || item.rawText }}</div>
              <div class="crop-preview-skill" :title="item.best?.skill.name || ''">{{ item.best?.skill.name || '—' }}</div>
              <div class="crop-preview-status-row">
                <span class="crop-preview-status">{{ getSkillStatusLabel(item.status) }}</span>
                <span class="crop-preview-score">{{ formatScore(item.best?.score) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty-state">加载中...</div>
    <div v-else-if="loadError" class="empty-state">加载 operators.json 失败: {{ loadError }}</div>

    <div v-else class="operators-grid" :class="{ 'e1-mode': e1Mode }">
      <template v-for="{ rarity, op } in filteredOperators" :key="op.name">
        <div class="operator-card" :class="{ selected: isSelected(op.name), 'low-gap': lowGapOperators.has(op.name) }" :data-rarity="getRarityNum(rarity)" @click="toggleOperator(op)">
          <div class="avatar-wrapper">
            <div class="rarity-badge">★{{ getRarityNum(rarity) }}</div>
            <img v-if="getAvatarUrl(op.avatar_url)" :src="getAvatarUrl(op.avatar_url)" :alt="op.name" loading="lazy" @error="handleImgError" />
            <div class="avatar-placeholder" style="display: none">{{ getFirstChar(op.name) }}</div>
          </div>
          <div class="operator-info">
            <div class="operator-name" :title="op.name">{{ op.name }}</div>
            <div class="operator-profession">{{ op.profession }}</div>
            <div v-if="skillDisplayMode === 0" class="skills-icon-row">
              <div v-for="idx in (e1Mode ? 2 : 3)" :key="idx" class="skill-icon-slot" :class="{ empty: !getVisibleSkills(op)[idx - 1], selected: getVisibleSkills(op)[idx - 1] && isSkillSelected(op.name + '::' + getVisibleSkills(op)[idx - 1].name) }" @click.stop="getVisibleSkills(op)[idx - 1] && toggleSkill(op.name, op.name + '::' + getVisibleSkills(op)[idx - 1].name)">
                <img v-if="getVisibleSkills(op)[idx - 1]" :src="getSkillIconUrl(getVisibleSkills(op)[idx - 1])" :alt="getVisibleSkills(op)[idx - 1].name" :title="getVisibleSkills(op)[idx - 1].name" class="skill-icon-img" @error="($event.target as HTMLImageElement).style.display='none'" />
              </div>
            </div>
            <div v-else class="skills-list">
              <template v-if="getVisibleSkills(op).length > 0">
                <span v-for="skill in getVisibleSkills(op)" :key="skill.skillId || skill.name" class="skill-tag" :class="{ selected: isSkillSelected(op.name + '::' + skill.name) }" :title="skill.name" @click.stop="toggleSkill(op.name, op.name + '::' + skill.name)">
                  <img :src="getSkillIconUrl(skill)" :alt="skill.name" class="skill-icon" @error="($event.target as HTMLImageElement).style.display='none'" />
                  {{ skill.name }}
                </span>
              </template>
              <span v-else class="no-skills">无技能</span>
            </div>
          </div>
        </div>
      </template>
      <div v-if="filteredOperators.length === 0" class="empty-state">没有符合条件的干员</div>
      <div class="bottom-spacer"></div>
    </div>
  </div>
</template>

<style scoped>
.operators-page { min-height: 100vh; background: #1a1a2e; color: #e0e0e0; position: relative; }
.filter-bar { position: sticky; top: 0; z-index: 100; background: #16213e; border-bottom: 2px solid #0f3460; padding: 12px 20px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4); display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.filter-left { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.filter-right { flex: 0 0 auto; display: flex; flex-direction: column; gap: 8px; align-items: flex-end; }
.filter-row { display: flex; align-items: center; gap: 10px}
.download-hint { font-size: 14px; color: #f0ad4e; line-height: 1; }
.download-progress-wrap { display: flex; flex-direction: column; gap: 3px; width: 232px; margin-right: 8px; }
.download-progress-text { font-size: 12px; color: #f0ad4e; white-space: nowrap; }
.download-progress-bar { width: 100%; height: 4px; background: #1e2a45; border-radius: 2px; overflow: hidden; }
.download-progress-fill { height: 100%; background: #f0ad4e; border-radius: 2px; transition: width 0.3s ease; }
.download-progress-time { font-size: 12px; color: #8899aa; }
.mode-toggle-btn { padding: 5px 12px; border: 1px solid #445577; border-radius: 5px; background: #1e2a45; color: #aaccee; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.mode-toggle-btn:hover { background: #2a3a5a; border-color: #6688bb; color: #ffffff; }
.mode-toggle-btn.active { background: #0f3460; border-color: #2980b9; color: #ffffff; }
.filter-label { font-size: 13px; color: #8899aa; min-width: 50px; user-select: none; }
.filter-group { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.filter-btn { display: inline-flex; align-items: center; padding: 5px 14px; border: 1px solid #334466; border-radius: 4px; background: #1a1a2e; color: #99aabb; font-size: 13px; cursor: pointer; transition: all 0.2s; user-select: none; white-space: nowrap; }
.filter-btn:hover { border-color: #5588bb; color: #ccddeeff; background: #223355; }
.filter-btn.active { background: #0f3460; border-color: #2980b9; color: #ffffff; box-shadow: 0 0 8px rgba(41, 128, 185, 0.3); }
.star-1.active { background: #555555; border-color: #888888; }
.star-2.active { background: #5a7a3a; border-color: #88aa55; }
.star-3.active { background: #3a5a7a; border-color: #5588bb; }
.star-4.active { background: #6a4a8a; border-color: #9966cc; }
.star-5.active { background: #8a7a2a; border-color: #ccaa33; }
.star-6.active { background: #8a4a2a; border-color: #ff8833; }
.paste-group { display: flex; align-items: stretch; }
.upload-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid #445566; border-right: none; border-radius: 4px 0 0 4px; background: #1e2a45; color: #aaccee; cursor: pointer; transition: all 0.2s; flex-shrink: 0; padding: 0; }
.upload-btn:hover:not(:disabled) { background: #2a3a5a; color: #ffffff; }
.upload-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.paste-input { width: 200px; height: 32px; line-height: 23px; padding: 4px 10px; border: 1px solid #445566; border-radius: 0 4px 4px 0; background: #1a1a2e; color: #aaccee; font-size: 13px; resize: none; outline: none; transition: border-color 0.2s; vertical-align: middle; box-sizing: border-box; overflow-y: hidden; }
.paste-input:focus { border-color: #2980b9; box-shadow: 0 0 6px rgba(41, 128, 185, 0.3); }
.paste-input:disabled { opacity: 0.5; cursor: not-allowed; }
.paste-input::placeholder { color: #556677; }
.reset-selection-btn { padding: 6px 16px; border: 1px solid #445566; border-radius: 4px; background: #1a2a3e; color: #99aabb; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.reset-selection-btn:hover:not(:disabled) { background: #223344; border-color: #557788; color: #ccddeeff; }
.reset-selection-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.generate-btn { margin-left: auto; padding: 6px 20px; border: 1px solid #2980b9; border-radius: 4px; background: #0f3460; color: #ffffff; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.generate-btn:hover:not(:disabled) { background: #2980b9; box-shadow: 0 0 8px rgba(41, 128, 185, 0.4); }
.generate-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.stats-bar { padding: 10px 20px; background: #1a1a2e; font-size: 13px; color: #667788; display: flex; align-items: center; gap: 16px; border-bottom: 1px solid #222244; }
.stats-bar .count { color: #2980b9; font-weight: bold; }
.selected-info { margin-left: auto; font-size: 12px; color: #889; }
.crop-preview-panel { border-bottom: 1px solid #222244; background: #151b2d; }
.crop-preview-toggle { width: 100%; display: flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; background: transparent; color: #99aabb; font-size: 13px; cursor: pointer; text-align: left; }
.crop-preview-toggle:hover { background: #1a2438; color: #ccddee; }
.crop-preview-chevron { display: inline-block; width: 1em; transition: transform 0.15s ease; color: #7799aa; }
.crop-preview-chevron.open { transform: rotate(90deg); }
.crop-preview-count { margin-left: auto; min-width: 20px; padding: 1px 8px; border-radius: 999px; background: #1e2a45; color: #88aacc; font-size: 12px; text-align: center; }
.crop-preview-body { padding: 0 20px 14px; }
.crop-preview-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.crop-preview-card { background: #1a2438; border: 1px solid #2a3a55; border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.crop-preview-card.status-low-gap,
.crop-preview-card.status-low-confidence,
.crop-preview-card.status-ambiguous { border-color: #885533; }
.crop-preview-card.status-out-of-bounds,
.crop-preview-card.status-no-skills { border-color: #445566; opacity: 0.85; }
.crop-preview-images { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.crop-preview-thumb { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.crop-preview-thumb img { width: 64px; height: 64px; object-fit: contain; background: #0f1524; border: 1px solid #2a3a55; border-radius: 6px; image-rendering: auto; }
.crop-preview-empty { width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; background: #0f1524; border: 1px dashed #334466; border-radius: 6px; color: #556677; font-size: 11px; }
.crop-preview-caption { font-size: 11px; color: #667788; }
.crop-preview-meta { min-width: 0; }
.crop-preview-name { font-size: 13px; font-weight: 600; color: #ddeeff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.crop-preview-skill { margin-top: 2px; font-size: 12px; color: #88aacc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.crop-preview-status-row { margin-top: 6px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.crop-preview-status { font-size: 11px; color: #99aabb; }
.crop-preview-score { font-size: 11px; color: #f0ad4e; font-variant-numeric: tabular-nums; }
.operators-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; padding: 16px 20px; }
.operator-card { background: #1e2a40; border: 2px solid #2a3a55; border-radius: 8px; overflow: hidden; cursor: pointer; transition: all 0.2s; position: relative; }
.operator-card.selected { border-color: #ff6600; box-shadow: 0 0 12px rgba(255, 102, 0, 0.3); }
.operator-card.selected::after { content: '✓'; position: absolute; top: 6px; right: 8px; font-size: 16px; color: #ff6600; font-weight: bold; text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8); z-index: 2; }
.operator-card.low-gap { animation: lowGapPulse 2s ease-in-out infinite; border-color: #ff4444 !important; }
.operator-card.low-gap::after { content: '⚠'; position: absolute; top: 6px; right: 8px; font-size: 16px; color: #ff4444; font-weight: bold; text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8); z-index: 2; }
@keyframes lowGapPulse {
  0%, 100% { box-shadow: 0 0 3px rgba(255, 0, 0, 0.3), 0 0 6px rgba(255, 0, 0, 0.15); }
  25% { box-shadow: 0 0 6px rgba(255, 0, 0, 0.5), 0 0 12px rgba(255, 0, 0, 0.25); }
  50% { box-shadow: 0 0 10px rgba(255, 0, 0, 0.7), 0 0 20px rgba(255, 0, 0, 0.35); }
  75% { box-shadow: 0 0 6px rgba(255, 0, 0, 0.5), 0 0 12px rgba(255, 0, 0, 0.25); }
}
.operator-card[data-rarity='1'] { border-color: #444; }
.operator-card[data-rarity='2'] { border-color: #556644; }
.operator-card[data-rarity='3'] { border-color: #335577; }
.operator-card[data-rarity='4'] { border-color: #664488; }
.operator-card[data-rarity='5'] { border-color: #887733; }
.operator-card[data-rarity='6'] { border-color: #885522; }
.operator-card[data-rarity='1'].selected, .operator-card[data-rarity='2'].selected, .operator-card[data-rarity='3'].selected, .operator-card[data-rarity='4'].selected, .operator-card[data-rarity='5'].selected, .operator-card[data-rarity='6'].selected { border-color: #ff6600; box-shadow: 0 0 10px rgba(255, 102, 0, 0.3); }
.avatar-wrapper { width: 100%; aspect-ratio: 1; background: #16213e; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; }
.avatar-wrapper img { width: 100%; height: 100%; object-fit: cover; }
.avatar-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 36px; font-weight: bold; color: #556677; background: linear-gradient(135deg, #1a2a3e, #16213e); }
.rarity-badge { position: absolute; top: 4px; left: 4px; background: rgba(0, 0, 0, 0.7); padding: 1px 6px; border-radius: 3px; font-size: 11px; color: #ffcc00; font-weight: bold; z-index: 1; }
.operator-info { padding: 8px 4px; }
.operator-name { font-size: 13px; font-weight: bold; color: #ddeeff; margin-bottom: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.operator-profession { font-size: 11px; color: #7799aa; margin-bottom: 6px; }
.skills-list { display: flex; flex-wrap: wrap; gap: 4px; }
.skill-tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; background: #162838; border: 1px solid #2a4055; border-radius: 3px; font-size: 13px; color: #88aacc; cursor: pointer; transition: all 0.15s; user-select: none; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-tag:hover { background: #1a3a55; border-color: #4488aa; color: #aaddee; }
.skill-tag.selected { background: #003318; border-color: #00cc44; color: #66ff99; box-shadow: 0 0 6px rgba(0, 204, 68, 0.35), 0 0 12px rgba(0, 204, 68, 0.15); }
.skill-icon { width: 18px; height: 18px; object-fit: contain; flex-shrink: 0; }
.skills-icon-row { display: flex; gap: 4px; padding: 2px; }
.skill-icon-slot { flex: 1; background: #16213e; border: 2px solid #2a3a55; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: background 0.15s, border-color 0.15s, box-shadow 0.15s; position: relative; padding: 0; line-height: 0; overflow: visible; }
.skill-icon-slot.empty { background: transparent; border-color: transparent; cursor: default; pointer-events: none; }
.skill-icon-slot:not(.empty):hover { background: #1a3050; border-color: #4488aa; }
.e1-mode .skill-icon-slot:not(.empty) { transform: scale(0.9); }
.skill-icon-slot.selected { z-index: 1; box-shadow: 0 0 8px rgba(0, 220, 80, 0.45), 0 0 16px rgba(0, 220, 80, 0.2); }
.skill-icon-slot.selected .skill-icon-img { transform: translateY(-4px); }
.skill-icon-slot.selected::before { content: ''; position: absolute; bottom: -2px; left: -2px; right: -2px; height: 4px; background: #00cc44; box-shadow: 0 0 6px rgba(0, 204, 68, 0.7), 0 0 12px rgba(0, 204, 68, 0.4); z-index: 3; }
.skill-icon-img { display: block; width: calc(100% + 4px); height: calc(100% + 4px); margin: -2px; object-fit: contain; }
.no-skills { font-size: 11px; color: #556; font-style: italic; }
.empty-state { text-align: center; padding: 60px 20px; color: #556677; font-size: 16px; grid-column: 1 / -1; }
.bottom-spacer { height: 40px; grid-column: 1 / -1; }
@media (max-width: 600px) {
  .operators-grid { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; padding: 10px; }
  .filter-bar { padding: 10px 12px; }
  .filter-btn { padding: 4px 10px; font-size: 12px; }
  .operator-name { font-size: 12px; }
  .skill-tag { font-size: 10px; padding: 1px 6px; }
}
</style>
