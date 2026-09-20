<template>
  <div class="page-container">
    <van-nav-bar :title="subjectName" left-arrow @click-left="router.back()" />

    <div class="page-content">
      <van-search
        v-model="searchKeyword"
        placeholder="搜索知识点"
        background="transparent"
        shape="round"
        @search="handleSearch"
      />

      <div v-if="loading" class="loading-container">
        <van-loading />
      </div>

      <div v-else-if="searchResults.length > 0" class="search-results">
        <div class="section-title">搜索结果</div>
        <div
          v-for="node in searchResults"
          :key="node.id"
          class="knowledge-item"
          @click="selectKnowledge(node)"
        >
          <span class="knowledge-name">{{ node.name }}</span>
          <span class="knowledge-count">{{ node.question_count }} 题</span>
        </div>
      </div>

      <div v-else class="knowledge-tree">
        <div v-for="(chapter, cIndex) in knowledgeTree" :key="chapter.id">
          <div class="tree-item level-1" @click="toggleChapter(cIndex)">
            <van-icon :name="expandedChapters.includes(cIndex) ? 'arrow-down' : 'arrow'" />
            <span class="tree-name">{{ chapter.name }}</span>
            <span class="tree-count">{{ chapter.question_count }} 题</span>
          </div>

          <div v-show="expandedChapters.includes(cIndex)">
            <div
              v-for="(section, sIndex) in chapter.children"
              :key="section.id"
            >
              <div
                class="tree-item level-2"
                @click="toggleSection(cIndex, sIndex)"
              >
                <van-icon :name="isSectionExpanded(cIndex, sIndex) ? 'arrow-down' : 'arrow'" />
                <span class="tree-name">{{ section.name }}</span>
                <span class="tree-count">{{ section.question_count }} 题</span>
              </div>

              <div v-show="isSectionExpanded(cIndex, sIndex)">
                <div
                  v-for="point in section.children"
                  :key="point.id"
                  class="tree-item level-3 clickable"
                  @click="selectKnowledge(point)"
                >
                  <span class="tree-dot"></span>
                  <span class="tree-name">{{ point.name }}</span>
                  <span class="tree-count">{{ point.question_count }} 题</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="practice-options card">
        <div class="section-title">练习模式</div>
        <div class="mode-grid">
          <div class="mode-item" @click="startPracticeClick('sequential')">
            <div class="mode-icon">📖</div>
            <span class="mode-name">顺序练习</span>
            <span class="mode-desc">按知识点顺序刷题</span>
          </div>
          <div class="mode-item" @click="startPracticeClick('random')">
            <div class="mode-icon">🎲</div>
            <span class="mode-name">随机练习</span>
            <span class="mode-desc">随机抽取题目练习</span>
          </div>
        </div>
      </div>
    </div>

    <van-popup
      v-model:show="showModeSelector"
      position="bottom"
      :style="{ height: '80%' }"
      round
    >
      <div class="mode-selector">
        <div class="selector-header">
          <div class="selector-title">
            {{ selectedMode === 'random' ? '随机练习配置' : '顺序练习配置' }}
          </div>
          <van-icon name="cross" @click="closeSelector" />
        </div>

        <div class="selector-content">
          <!-- 经典配置：题目数量 + 单一难度范围（保留原有启动方式） -->
          <template v-if="!isQuotaMode">
            <div class="selector-item">
              <div class="selector-label">题目数量</div>
              <van-radio-group v-model="selectedCount">
                <van-radio name="10">10 题</van-radio>
                <van-radio name="20">20 题</van-radio>
                <van-radio name="50">50 题</van-radio>
              </van-radio-group>
            </div>

            <div class="selector-item">
              <div class="selector-label">难度范围</div>
              <van-radio-group v-model="selectedDifficulty">
                <van-radio name="">全部难度</van-radio>
                <van-radio name="easy">简单</van-radio>
                <van-radio name="medium">中等</van-radio>
                <van-radio name="hard">困难</van-radio>
              </van-radio-group>
            </div>
          </template>

          <!-- 配额配置：填写简单/中等/困难三档题数 -->
          <template v-else>
            <div class="selector-item">
              <div class="selector-label">按难度配额抽题</div>
              <div class="quota-tip">
                分别填写三档题数，某档题量不足时按 中等 → 简单 → 困难 顺序自动补位；
                补不齐则整批取消，不会生成不完整的练习。
              </div>

              <div class="quota-row" v-for="item in quotaRows" :key="item.level">
                <span class="quota-name" :class="'diff-' + item.level">{{ item.label }}</span>
                <van-stepper
                  v-model="quotaCounts[item.level]"
                  :min="0"
                  :max="200"
                  :step="item.step"
                  button-size="28"
                  integer
                />
                <span class="quota-need">需 {{ quotaCounts[item.level] }} 题</span>
              </div>

              <div class="quota-total">
                三档合计：<b>{{ quotaTotal }}</b> 题
                <span v-if="quotaTotal === 0" class="quota-warn">（总题数需大于 0）</span>
              </div>
            </div>

            <!-- 创建成功：实际补位结果快照 -->
            <div v-if="quotaReport" class="quota-panel success">
              <div class="panel-title">✓ 已创建，实际抽题结果</div>
              <div class="panel-row" v-for="item in quotaRows" :key="item.level">
                <span class="panel-name">{{ item.label }}</span>
                <span>需求 {{ levelStat(item.level).requested }}</span>
                <span>可用 {{ levelStat(item.level).available }}</span>
                <span>实得 {{ levelStat(item.level).allocated }}</span>
                <span v-if="levelStat(item.level).filled" class="panel-fill">
                  补入 {{ levelStat(item.level).filled }}
                </span>
              </div>
              <div v-if="quotaReport.transfers.length" class="panel-transfers">
                <div v-for="(t, i) in quotaReport.transfers" :key="i" class="transfer-line">
                  {{ difficultyName(t.from_difficulty) }} 补 {{ difficultyName(t.to_difficulty) }}
                  {{ t.count }} 题
                </div>
              </div>
              <div v-else class="panel-transfers muted">三档均按需求抽满，未发生补位</div>
            </div>

            <!-- 整批拒绝：每档需求、可用数和缺口 -->
            <div v-if="quotaShortage" class="quota-panel shortage">
              <div class="panel-title">✗ {{ quotaShortage.message }}</div>
              <div class="panel-row" v-for="item in quotaRows" :key="item.level">
                <span class="panel-name">{{ item.label }}</span>
                <span>需求 {{ shortageLevel(item.level).requested }}</span>
                <span>可用 {{ shortageLevel(item.level).available }}</span>
                <span class="panel-gap">缺口 {{ shortageLevel(item.level).shortage }}</span>
              </div>
              <div class="panel-summary">
                总需求 {{ quotaShortage.total_requested }} 题，
                总可用 {{ quotaShortage.total_available }} 题，
                共缺 {{ quotaShortage.total_shortage }} 题
              </div>
            </div>
          </template>
        </div>

        <div class="selector-footer">
          <van-button
            v-if="selectedMode === 'random'"
              plain
              block
              round
              class="switch-btn"
              @click="toggleDrawMode"
            >
              {{ isQuotaMode ? '切换为经典随机（数量+难度范围）' : '切换为按难度配额抽题' }}
            </van-button>
          <!-- 配额创建成功：确认实际补位结果后进入 -->
          <van-button
            v-if="isQuotaMode && quotaReport"
            block
            type="success"
            round
            @click="enterQuotaSession"
          >
            进入练习（共 {{ quotaReport.total_requested }} 题）
          </van-button>
          <!-- 整批拒绝：允许修改三档数量后重新创建 -->
          <van-button
            v-else-if="isQuotaMode && quotaShortage"
            block
            plain
            round
            @click="resetQuotaPanels"
          >
            修改三档数量后重试
          </van-button>
          <van-button
            v-else
            block
            type="primary"
            round
            :loading="starting"
            @click="confirmStartPractice"
          >
            {{ isQuotaMode ? '按配额创建并开始' : '开始练习' }}
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showLoadingToast, closeToast, showToast } from 'vant'
import { getKnowledgeTree, searchKnowledge } from '@/api/knowledge'
import { getSubjects } from '@/api/knowledge'
import {
  startPractice,
  getQuotaShortage,
  type StartPracticeResponse
} from '@/api/practice'
import type {
  KnowledgeNode,
  Subject,
  DifficultyLevel,
  QuotaReport,
  QuotaShortageDetail
} from '@/types'

const route = useRoute()
const router = useRouter()

const subjectId = computed(() => route.params.subjectId as string)

const loading = ref(true)
const searchKeyword = ref('')
const subjectName = ref('')
const knowledgeTree = ref<KnowledgeNode[]>([])
const searchResults = ref<KnowledgeNode[]>([])
const expandedChapters = ref<number[]>([0])
const expandedSections = ref<Record<string, boolean>>({})

const showModeSelector = ref(false)
const selectedMode = ref('')
const selectedKnowledge = ref<KnowledgeNode | null>(null)
const selectedCount = ref('10')
const selectedDifficulty = ref('')

// 随机练习：false=经典（数量+难度范围，保留原启动方式），true=按难度配额
const isQuotaMode = ref(false)
const starting = ref(false)
const quotaReport = ref<QuotaReport | null>(null)
const quotaShortage = ref<QuotaShortageDetail | null>(null)

const quotaRows = [
  { level: 'easy' as DifficultyLevel, label: '简单', step: 1 },
  { level: 'medium' as DifficultyLevel, label: '中等', step: 1 },
  { level: 'hard' as DifficultyLevel, label: '困难', step: 1 }
]

const quotaCounts = reactive<Record<DifficultyLevel, number>>({
  easy: 4,
  medium: 4,
  hard: 2
})

const quotaTotal = computed(() =>
  quotaCounts.easy + quotaCounts.medium + quotaCounts.hard
)

const difficultyName = (level: DifficultyLevel) => {
  const map: Record<DifficultyLevel, string> = {
    easy: '简单',
    medium: '中等',
    hard: '困难'
  }
  return map[level]
}

const levelStat = (level: DifficultyLevel) => {
  return quotaReport.value!.levels[level]
}

const shortageLevel = (level: DifficultyLevel) => {
  return quotaShortage.value!.levels[level]
}

const resetQuotaPanels = () => {
  quotaReport.value = null
  quotaShortage.value = null
}

const toggleDrawMode = () => {
  isQuotaMode.value = !isQuotaMode.value
  resetQuotaPanels()
}

const closeSelector = () => {
  showModeSelector.value = false
  resetQuotaPanels()
}

const fetchData = async () => {
  try {
    showLoadingToast({ message: '加载中...', duration: 0 })
    const [subjects, tree] = await Promise.all([
      getSubjects(),
      getKnowledgeTree(subjectId.value)
    ])

    const subject = subjects.find((s: Subject) => s.id === subjectId.value)
    subjectName.value = subject?.name || '题库'
    knowledgeTree.value = tree
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
    closeToast()
  }
}

const toggleChapter = (index: number) => {
  const i = expandedChapters.value.indexOf(index)
  if (i > -1) {
    expandedChapters.value.splice(i, 1)
  } else {
    expandedChapters.value.push(index)
  }
}

const isSectionExpanded = (cIndex: number, sIndex: number) => {
  return expandedSections.value[`${cIndex}-${sIndex}`]
}

const toggleSection = (cIndex: number, sIndex: number) => {
  const key = `${cIndex}-${sIndex}`
  expandedSections.value[key] = !expandedSections.value[key]
}

const handleSearch = async () => {
  if (!searchKeyword.value.trim()) {
    searchResults.value = []
    return
  }

  try {
    searchResults.value = await searchKnowledge(subjectId.value, searchKeyword.value.trim())
  } catch (error) {
    console.error(error)
  }
}

const selectKnowledge = (node: KnowledgeNode) => {
  if (node.question_count === 0) {
    showToast('该知识点下暂无题目')
    return
  }
  selectedKnowledge.value = node
  openSelector('random')
}

const startPracticeClick = (mode: string) => {
  // 从练习模式卡片进入：不绑定具体知识点，范围为整个学科
  selectedKnowledge.value = null
  openSelector(mode)
}

const openSelector = (mode: string) => {
  selectedMode.value = mode
  // 每次重新打开设置弹窗都回到经典配置，保留原有数量+难度范围的启动方式
  isQuotaMode.value = false
  resetQuotaPanels()
  pendingSession.value = null
  showModeSelector.value = true
}

const enterPracticePage = (startResult: StartPracticeResponse) => {
  showModeSelector.value = false
  resetQuotaPanels()
  // 成功创建后按题号快照继续，只携带 session_id，由会话快照驱动答题
  router.push({
    path: `/practice/${selectedMode.value}`,
    query: {
      subjectId: subjectId.value,
      knowledgeIds: selectedKnowledge.value?.id || '',
      sessionId: startResult.session_id
    }
  })
}

const confirmStartPractice = async () => {
  const knowledgeIds = selectedKnowledge.value?.id
    ? [selectedKnowledge.value.id]
    : undefined

  // 经典配置：直接跳转，沿用原有 /practice/:mode 启动方式
  if (!isQuotaMode.value) {
    showModeSelector.value = false
    router.push({
      path: `/practice/${selectedMode.value}`,
      query: {
        subjectId: subjectId.value,
        knowledgeIds: selectedKnowledge.value?.id || '',
        count: selectedCount.value,
        difficulty: selectedDifficulty.value
      }
    })
    return
  }

  if (quotaTotal.value <= 0) {
    showToast('请至少填写一道题')
    return
  }

  starting.value = true
  resetQuotaPanels()
  try {
    const result = await startPractice({
      mode: 'random',
      subject_id: subjectId.value,
      knowledge_ids: knowledgeIds,
      question_count: quotaTotal.value,
      easy_count: quotaCounts.easy,
      medium_count: quotaCounts.medium,
      hard_count: quotaCounts.hard
    })
    // 创建成功：在设置页展示实际补位结果，确认后再进入答题
    quotaReport.value = result.quota_report || null
    showToast({ type: 'success', message: '练习已按配额创建' })
    pendingSession.value = result
  } catch (error: any) {
    // 整批拒绝：展示每档需求、可用数和缺口，不跳转、不产生短会话
    const shortage = getQuotaShortage(error)
    if (shortage) {
      quotaShortage.value = shortage
    }
  } finally {
    starting.value = false
  }
}

// 配额创建成功、用户查看补位结果后点击进入
const pendingSession = ref<StartPracticeResponse | null>(null)

const enterQuotaSession = () => {
  if (pendingSession.value) {
    enterPracticePage(pendingSession.value)
    pendingSession.value = null
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.tree-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: white;
  border-radius: 10px;
  margin-bottom: 8px;
  cursor: pointer;
}

.tree-item.level-1 {
  font-weight: 600;
  color: #1a1a2e;
  background: #f8fafc;
}

.tree-item.level-2 {
  margin-left: 16px;
  color: #334155;
}

.tree-item.level-3 {
  margin-left: 32px;
  color: #64748b;
  background: #fefefe;
}

.tree-item.clickable:active {
  background: #eff6ff;
}

.tree-name {
  flex: 1;
  font-size: 15px;
  margin-left: 8px;
}

.tree-count {
  font-size: 12px;
  color: #94a3b8;
}

.tree-dot {
  width: 6px;
  height: 6px;
  background: #3b82f6;
  border-radius: 50%;
  margin-left: 8px;
}

.knowledge-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: white;
  border-radius: 10px;
  margin-bottom: 8px;
}

.knowledge-name {
  font-size: 15px;
  color: #1a1a2e;
}

.knowledge-count {
  font-size: 12px;
  color: #3b82f6;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 8px;
}

.mode-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 12px;
  background: #f8fafc;
  border-radius: 14px;
  cursor: pointer;
}

.mode-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.mode-name {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 4px;
}

.mode-desc {
  font-size: 12px;
  color: #94a3b8;
}

.mode-selector {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #f1f5f9;
}

.selector-title {
  font-size: 16px;
  font-weight: 600;
}

.selector-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.selector-item {
  margin-bottom: 24px;
}

.selector-label {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 12px;
}

.selector-footer {
  padding: 16px;
  border-top: 1px solid #f1f5f9;
}

.switch-btn {
  margin-bottom: 10px;
  color: #1d4ed8;
}

.quota-tip {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.7;
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 16px;
}

.quota-row {
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f1f5f9;
}

.quota-name {
  width: 52px;
  font-size: 15px;
  font-weight: 600;
}

.quota-name.diff-easy {
  color: #16a34a;
}

.quota-name.diff-medium {
  color: #d97706;
}

.quota-name.diff-hard {
  color: #dc2626;
}

.quota-need {
  margin-left: auto;
  font-size: 13px;
  color: #64748b;
}

.quota-total {
  margin-top: 14px;
  font-size: 14px;
  color: #334155;
}

.quota-total b {
  color: #1d4ed8;
  font-size: 18px;
}

.quota-warn {
  color: #dc2626;
  margin-left: 6px;
}

.quota-panel {
  border-radius: 12px;
  padding: 14px;
  margin-top: 8px;
}

.quota-panel.success {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
}

.quota-panel.shortage {
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}

.quota-panel.success .panel-title {
  color: #15803d;
}

.quota-panel.shortage .panel-title {
  color: #b91c1c;
}

.panel-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #475569;
  padding: 6px 0;
  border-bottom: 1px dashed #e2e8f0;
}

.panel-name {
  font-weight: 600;
  width: 40px;
  color: #1a1a2e;
}

.panel-fill {
  color: #15803d;
  font-weight: 600;
}

.panel-gap {
  color: #dc2626;
  font-weight: 600;
}

.panel-transfers {
  margin-top: 10px;
  font-size: 13px;
  color: #1d4ed8;
  line-height: 1.8;
}

.panel-transfers.muted {
  color: #94a3b8;
}

.panel-summary {
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #b91c1c;
}
</style>
