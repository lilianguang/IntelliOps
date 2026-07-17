<template>
  <div>
    <h2>{{ pageTitle }}</h2>
    <el-card style="margin-bottom:15px">
      <el-form :inline="true" :model="filter">
        <el-form-item label="风险等级">
          <el-select v-model="filter.risk_level" clearable placeholder="全部">
            <el-option label="严重" value="critical" />
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部">
            <el-option label="新" value="new" />
            <el-option label="已确认" value="acknowledged" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已忽略" value="ignored" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备">
          <el-select v-model="filter.source_device" clearable filterable placeholder="全部">
            <el-option v-for="d in deviceList" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" v-if="isHistory">
          <el-radio-group v-model="timePreset" size="small" @change="onTimePresetChange">
            <el-radio-button label="3">近3天</el-radio-button>
            <el-radio-button label="7">近7天</el-radio-button>
            <el-radio-button label="30">近30天</el-radio-button>
            <el-radio-button label="custom">自定义</el-radio-button>
          </el-radio-group>
          <el-date-picker
            v-if="timePreset === 'custom'"
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            :clearable="false"
            @change="load(1)"
            style="width:360px;margin-left:8px"
          />
        </el-form-item>
        <el-form-item v-if="isRealtime">
          <el-tag type="info" size="small">最近 24 小时，每 30 秒自动刷新</el-tag>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 批量操作栏 -->
    <el-card v-if="selectedIds.length > 0" style="margin-bottom:10px">
      <div style="display:flex;align-items:center;gap:12px">
        <span>已选 <strong>{{ selectedIds.length }}</strong> 条</span>
        <el-button size="small" @click="batchUpdate('acknowledged')">批量确认</el-button>
        <el-button size="small" type="success" @click="batchUpdate('resolved')">批量解决</el-button>
        <el-button size="small" type="info" @click="batchUpdate('ignored')">批量忽略</el-button>
        <el-button size="small" text @click="clearSelection">取消选择</el-button>
      </div>
    </el-card>

    <el-table ref="tableRef" :data="events" stripe @row-click="showDetail" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="45" />
      <el-table-column prop="last_seen" label="时间" width="170">
        <template #default="{row}">{{ (row.last_seen||'').substring(0,19) }}</template>
      </el-table-column>
      <el-table-column label="级别" width="90">
        <template #default="{row}"><el-tag :type="riskTag(row.risk_level)" size="small">{{ row.risk_level }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="source_device" label="设备" width="150" />
      <el-table-column prop="event_type" label="类型" width="120" />
      <el-table-column prop="summary" label="摘要" min-width="220">
        <template #default="{row}">
          <el-tooltip :content="row.summary" placement="top" :show-after="300" :disabled="!row.summary || row.summary.length < 60">
            <div class="summary-cell" @click.stop="showDetail(row)">{{ row.summary }}</div>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{row}"><el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{row}">
          <el-button text size="small" @click.stop="updateStatus(row.event_id,'acknowledged')">确认</el-button>
          <el-button text size="small" type="success" @click.stop="updateStatus(row.event_id,'resolved')">解决</el-button>
          <el-button text size="small" type="info" @click.stop="updateStatus(row.event_id,'ignored')">忽略</el-button>
          <el-button text size="small" type="primary" @click.stop="goAnalyze(row.event_id)">分析</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="text-align:center;margin-top:15px">
      <el-pagination background layout="prev,pager,next,total" :total="total" :page-size="pageSize" @current-change="load" />
    </div>

    <!-- 事件详情抽屉 -->
    <el-drawer v-model="detailVisible" title="事件详情" size="600px" destroy-on-close>
      <div v-if="detailLoading" v-loading="detailLoading" style="padding:20px" />
      <div v-else-if="detail" class="detail-body">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="事件ID">{{ detail.event_id }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="riskTag(detail.risk_level)" size="small">{{ detail.risk_level }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(detail.status)" size="small">{{ detail.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="设备">{{ detail.source_device || '-' }}</el-descriptions-item>
          <el-descriptions-item label="源IP">{{ detail.source_ip || '-' }}</el-descriptions-item>
          <el-descriptions-item label="累计触发">{{ detail.occurrence_count || 1 }} 次</el-descriptions-item>
          <el-descriptions-item label="首次发现">{{ detail.first_seen }}</el-descriptions-item>
          <el-descriptions-item label="最近发现">{{ detail.last_seen }}</el-descriptions-item>
          <el-descriptions-item label="事件类型">{{ detail.event_type }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section">
          <div class="detail-label">摘要</div>
          <div class="detail-content">{{ detail.summary }}</div>
        </div>

        <div v-if="detail.raw_log" class="detail-section">
          <div class="detail-label">原始日志 / 指标</div>
          <pre class="detail-code">{{ formatRawLog(detail.raw_log) }}</pre>
        </div>

        <div v-if="detail.ai_report" class="detail-section">
          <div class="detail-label">AI 分析报告</div>
          <pre class="detail-code">{{ formatAiReport(detail.ai_report) }}</pre>
        </div>

        <div style="margin-top:20px">
          <el-button type="primary" @click="goAnalyze(detail.event_id)">AI 流式分析</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { eventApi } from '../api/index.js'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const isRealtime = computed(() => route.path === '/events/realtime')
const isHistory = computed(() => route.path === '/events/history')
const pageTitle = computed(() => isRealtime.value ? '实时事件' : (isHistory.value ? '历史事件' : '事件中心'))

const events = ref([])
const total = ref(0)
const pageSize = ref(20)
const filter = ref({ risk_level: '', status: '', source_device: '' })
const deviceList = ref([])
const tableRef = ref(null)
const selectedIds = ref([])

const timePreset = ref('7')
const timeRange = ref([])

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

let refreshTimer = null

const riskTag = (l) => ({ low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[l] || 'info')
const statusTag = (s) => ({ new: 'danger', acknowledged: 'warning', resolved: 'success', ignored: 'info' }[s] || 'info')

const fmt = (d) => {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const buildTimeRange = () => {
  const end = new Date()
  const start = new Date()
  if (isRealtime.value) {
    start.setHours(end.getHours() - 24)
    return [fmt(start), fmt(end)]
  }
  if (timePreset.value === 'custom') {
    return timeRange.value && timeRange.value.length === 2 ? timeRange.value : ['', '']
  }
  const days = Number(timePreset.value) || 7
  start.setDate(end.getDate() - (days - 1))
  start.setHours(0, 0, 0, 0)
  end.setHours(23, 59, 59, 0)
  return [fmt(start), fmt(end)]
}

const onTimePresetChange = () => {
  if (timePreset.value === 'custom') {
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - 6)
    start.setHours(0, 0, 0, 0)
    end.setHours(23, 59, 59, 0)
    timeRange.value = [fmt(start), fmt(end)]
  }
  load(1)
}

const load = async (page = 1) => {
  try {
    const params = { page, page_size: pageSize.value, ...filter.value }
    if (isRealtime.value || isHistory.value) {
      const [st, et] = buildTimeRange()
      if (st) params.start_time = st
      if (et) params.end_time = et
    }
    const r = await eventApi.list(params)
    events.value = r.data.items
    total.value = r.data.total
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  if (isRealtime.value) {
    timePreset.value = '1'
    refreshTimer = setInterval(() => load(1), 30000)
  } else if (isHistory.value) {
    timePreset.value = '7'
  }
  load()
  eventApi.devices().then(r => { deviceList.value = r.data.devices || [] }).catch(() => {})
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const updateStatus = async (id, s) => {
  try {
    await eventApi.updateStatus(id, s)
    ElMessage.success('状态更新成功')
    load()
  } catch (e) {
    ElMessage.error('状态更新失败')
    console.error(e)
  }
}

const batchUpdate = async (s) => {
  try {
    await eventApi.batchUpdateStatus(selectedIds.value, s)
    ElMessage.success(`已批量更新 ${selectedIds.value.length} 条事件`)
    clearSelection()
    load()
  } catch (e) {
    ElMessage.error('批量更新失败')
    console.error(e)
  }
}

const onSelectionChange = (rows) => {
  selectedIds.value = rows.map(r => r.event_id)
}

const clearSelection = () => {
  selectedIds.value = []
  tableRef.value?.clearSelection()
}

const showDetail = async (row) => {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const r = await eventApi.get(row.event_id)
    detail.value = r.data
  } catch (e) {
    ElMessage.error('加载事件详情失败')
    console.error(e)
  } finally {
    detailLoading.value = false
  }
}

const goAnalyze = (eventId) => {
  router.push(`/events/analysis?id=${eventId}`)
}

const formatRawLog = (raw) => {
  if (!raw) return ''
  try {
    const obj = JSON.parse(raw)
    return JSON.stringify(obj, null, 2)
  } catch {
    return raw
  }
}

const formatAiReport = (report) => {
  if (!report) return ''
  if (typeof report === 'string') {
    try {
      const obj = JSON.parse(report)
      return JSON.stringify(obj, null, 2)
    } catch {
      return report
    }
  }
  return JSON.stringify(report, null, 2)
}
</script>

<style scoped>
.summary-cell {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.5;
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.summary-cell:hover {
  color: var(--el-color-primary);
}
.detail-body {
  padding: 0 0 20px 0;
}
.detail-section {
  margin-top: 20px;
}
.detail-label {
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.detail-content {
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.detail-code {
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}
</style>
