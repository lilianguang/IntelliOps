<template>
  <div class="event-analysis-page">
    <h2>事件分析</h2>

    <el-card v-if="!eventId" style="margin-top:20px">
      <template #header>选择要分析的事件</template>
      <div style="color:#909399;padding:20px 0">请从事件列表点击“分析”按钮，或直接访问 <code>/events/analysis?id=事件ID</code></div>
      <el-button type="primary" @click="$router.push('/events/realtime')">前往事件中心</el-button>
    </el-card>

    <template v-else>
      <el-card style="margin-bottom:20px">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <span>事件信息</span>
            <el-button text type="primary" size="small" @click="$router.push('/events/realtime')">返回事件中心</el-button>
          </div>
        </template>
        <el-descriptions :column="2" border v-if="event">
          <el-descriptions-item label="事件ID">{{ event.event_id }}</el-descriptions-item>
          <el-descriptions-item label="事件类型">{{ event.event_type }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="riskTag(event.risk_level)" size="small">{{ event.risk_level }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(event.status)" size="small">{{ event.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="设备">{{ event.source_device || '-' }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ event.last_seen }}</el-descriptions-item>
          <el-descriptions-item label="摘要" :span="2">{{ event.summary || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-else v-loading="loadingEvent" style="height:120px" />
      </el-card>

      <el-card>
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <span>AI 流式分析</span>
            <div style="display:flex;gap:10px">
              <el-button v-if="streaming" size="small" type="danger" @click="stopAnalyze">停止</el-button>
              <el-button v-else size="small" type="primary" :disabled="!eventId" @click="startAnalyze">开始分析</el-button>
            </div>
          </div>
        </template>
        <div v-if="analysisHtml" class="analysis-content" v-html="analysisHtml" />
        <div v-else-if="streaming" class="analysis-placeholder">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>AI 正在分析中...</span>
        </div>
        <div v-else class="analysis-placeholder">点击“开始分析”按钮，AI 将基于事件信息进行推理分析</div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute } from 'vue-router'
import { eventApi } from '../../api/index.js'
import MarkdownIt from 'markdown-it'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const route = useRoute()
const eventId = computed(() => route.query.id)

const event = ref(null)
const loadingEvent = ref(false)
const analysisText = ref('')
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const analysisHtml = computed(() => analysisText.value ? md.render(analysisText.value) : '')
const streaming = ref(false)
let abortController = null

const riskTag = (l) => ({ low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[l] || 'info')
const statusTag = (s) => ({ new: 'danger', acknowledged: 'warning', resolved: 'success', ignored: 'info' }[s] || 'info')

const loadEvent = async () => {
  if (!eventId.value) return
  loadingEvent.value = true
  try {
    const r = await eventApi.get(eventId.value)
    event.value = r.data
  } catch (e) {
    ElMessage.error('加载事件详情失败')
    console.error(e)
  } finally {
    loadingEvent.value = false
  }
}

const startAnalyze = () => {
  if (!eventId.value) return
  analysisText.value = ''
  streaming.value = true

  abortController = eventApi.analyzeStream(eventId.value, {
    onMeta: () => {},
    onContent: (chunk) => {
      analysisText.value += chunk
    },
    onFinish: () => {
      streaming.value = false
      ElMessage.success('分析完成')
    },
    onError: (msg) => {
      streaming.value = false
      ElMessage.error(`分析失败：${msg}`)
    },
  })
}

const stopAnalyze = () => {
  abortController?.abort()
  streaming.value = false
}

onMounted(() => {
  loadEvent()
  if (eventId.value) {
    startAnalyze()
  }
})

onBeforeUnmount(() => {
  stopAnalyze()
})
</script>

<style scoped>
.event-analysis-page { padding: 4px; }
.analysis-content {
  background: var(--el-fill-color-light);
  padding: 16px;
  border-radius: 4px;
  min-height: 200px;
  line-height: 1.8;
}
.analysis-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #909399;
  min-height: 200px;
}
</style>
