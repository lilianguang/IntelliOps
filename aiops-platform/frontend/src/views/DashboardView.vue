<template>
  <div class="aiops-center">
    <h2 class="page-title">AI运营中心</h2>

    <!-- 第一行：核心指标卡片 -->
    <el-row :gutter="16" style="margin-bottom:20px">
      <el-col :span="6" v-for="(item, idx) in metricCards" :key="item.key">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-top">
            <div class="metric-icon" :style="{ background: item.bg }">
              <el-icon :size="20" :color="item.color"><component :is="item.icon" /></el-icon>
            </div>
            <div class="metric-status" :style="{ background: item.statusColor, color: '#fff' }">{{ item.statusText }}</div>
          </div>
          <div class="metric-value-wrap">
            <span class="metric-value">{{ item.value }}</span>
            <span class="metric-unit" v-if="item.unit">{{ item.unit }}</span>
          </div>
          <div class="metric-label">{{ item.label }}</div>
          <div class="sparkline-wrap" v-if="item.trend && item.trend.length">
            <div :ref="el => sparklineEls[idx] = el" class="sparkline"></div>
          </div>
          <div v-if="item.sub" class="metric-sub">{{ item.sub }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第二行：今日AI报告 + 风险热力图 -->
    <el-row :gutter="16" style="margin-bottom:20px">
      <el-col :span="16">
        <el-card shadow="hover" class="full-height-card">
          <template #header>
            <div style="display:flex;align-items:center;gap:8px">
              <el-icon><Document /></el-icon>
              <span>今日 AI 报告</span>
            </div>
          </template>
          <div v-if="dailySummary" class="daily-summary">
            <div class="summary-text">{{ dailySummary.summary }}</div>
            <div class="report-split">
              <!-- 监控规则：图标方式 -->
              <div class="report-left">
                <div class="section-title">监控规则</div>
                <div class="rules-icon-grid" v-if="dailySummary.rules_stats?.length">
                  <div v-for="r in dailySummary.rules_stats" :key="r.type" class="rule-icon-item" :title="`${r.type}: ${r.count}条`">
                    <div class="rule-icon-circle" :style="{ background: getRuleColor(r.type, 0.12), color: getRuleColor(r.type, 1) }">
                      <component :is="getRuleIcon(r.type)" />
                    </div>
                    <div class="rule-icon-name">{{ r.type }}</div>
                    <div class="rule-icon-count">{{ r.count }}条</div>
                  </div>
                </div>
                <div v-else style="color:#c0c4cc;font-size:13px;padding:20px 0">暂无规则数据</div>
              </div>
              <!-- 高危事件 -->
              <div class="report-right">
                <div class="section-title">高危事件 TOP</div>
                <div v-if="dailySummary.high_risk_events?.length" class="high-risk-list">
                  <div v-for="(e, idx) in dailySummary.high_risk_events" :key="idx" class="high-risk-item" @click="showEventDetail(e)">
                    <el-tag size="small" :type="riskTag(e.risk)">{{ e.type }}</el-tag>
                    <span class="high-risk-summary">{{ e.summary }}</span>
                    <span class="high-risk-time">{{ (e.last_seen || '').substring(5, 16) }}</span>
                  </div>
                </div>
                <div v-else style="color:#c0c4cc;font-size:13px;padding:20px 0">暂无高危事件</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="full-height-card">
          <template #header>
            <div style="display:flex;align-items:center;gap:8px">
              <el-icon><WarningFilled /></el-icon>
              <span>风险热力图</span>
            </div>
          </template>
          <div class="heatmap-wrap" v-if="heatmapData.length">
            <div v-for="h in heatmapData" :key="h.domain" class="heatmap-row">
              <div class="heatmap-domain">{{ h.domain }}</div>
              <div class="heatmap-cells">
                <div class="hm-cell" :style="{ background: heatColor(h.critical, h.total) }">严重 {{ h.critical }}</div>
                <div class="hm-cell" :style="{ background: heatColor(h.high, h.total) }">高 {{ h.high }}</div>
                <div class="hm-cell" :style="{ background: heatColor(h.medium, h.total) }">中 {{ h.medium }}</div>
                <div class="hm-cell" :style="{ background: heatColor(h.low, h.total) }">低 {{ h.low }}</div>
              </div>
              <div class="heatmap-total">共{{ h.total }}</div>
            </div>
          </div>
          <div v-else style="color:#c0c4cc;font-size:13px;text-align:center;padding:40px 0">暂无风险数据</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第三行：最近趋势 -->
    <el-card style="margin-bottom:20px">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
          <span>最近趋势</span>
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <el-radio-group v-model="granularity" size="small" @change="onGranularityChange">
              <el-radio-button label="day">按天</el-radio-button>
              <el-radio-button label="hour">按小时</el-radio-button>
            </el-radio-group>
            <el-radio-group v-model="dateRange" size="small" @change="onPresetChange">
              <el-radio-button v-for="p in presetOptions" :key="p.value" :label="p.value">{{ p.label }}</el-radio-button>
              <el-radio-button label="custom">自定义</el-radio-button>
            </el-radio-group>
            <el-date-picker
              v-model="dateRange0"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              size="small"
              value-format="YYYY-MM-DD"
              :clearable="false"
              @change="loadTrend"
              style="width:260px"
            />
            <el-button size="small" type="primary" :loading="trendLoading" @click="loadTrend">刷新</el-button>
            <el-tag type="info" size="small">合计 {{ trendTotal }}</el-tag>
          </div>
        </div>
      </template>
      <div ref="trendChart" style="width:100%;height:340px"></div>
    </el-card>

    <!-- 第四行：最近告警事件 + 快捷入口（高度一致） -->
    <el-row :gutter="20" class="align-row">
      <el-col :span="16">
        <el-card class="full-height-card">
          <template #header>
            <div style="display:flex;align-items:center;justify-content:space-between">
              <span>最近告警事件</span>
              <el-button text type="primary" size="small" @click="$router.push('/events')">查看更多</el-button>
            </div>
          </template>
          <el-table :data="events" stripe style="width:100%" size="small">
            <el-table-column prop="time" label="时间" width="160" />
            <el-table-column label="级别" width="80">
              <template #default="{row}"><el-tag :type="riskTag(row.risk_level)" size="small">{{ row.risk_level }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="source_device" label="设备" width="140" />
            <el-table-column label="摘要" min-width="260">
              <template #default="{row}">
                <span>{{ row.summary }}</span>
                <el-tag v-if="row.occurrence_count > 1" size="small" type="warning" style="margin-left:6px">{{ row.occurrence_count }}次</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="full-height-card">
          <template #header>快捷入口</template>
          <div class="quick-entry-grid">
            <div class="quick-entry-item" @click="$router.push('/ai-center/assistant')">
              <el-icon :size="22" color="#409eff"><ChatDotRound /></el-icon>
              <span>AI对话</span>
            </div>
            <div class="quick-entry-item" @click="$router.push('/ai-center/reports')">
              <el-icon :size="22" color="#67c23a"><Document /></el-icon>
              <span>AI报告</span>
            </div>
            <div class="quick-entry-item" @click="$router.push('/netinsight')">
              <el-icon :size="22" color="#e6a23c"><Promotion /></el-icon>
              <span>配置分析</span>
            </div>
            <div class="quick-entry-item" @click="$router.push('/events/statistics')">
              <el-icon :size="22" color="#909399"><PieChart /></el-icon>
              <span>事件统计</span>
            </div>
            <div class="quick-entry-item" @click="$router.push('/admin/rules')">
              <el-icon :size="22" color="#f56c6c"><List /></el-icon>
              <span>规则配置</span>
            </div>
            <div class="quick-entry-item" @click="$router.push('/admin/skills')">
              <el-icon :size="22" color="#409eff"><Monitor /></el-icon>
              <span>技能管理</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 高危事件详情抽屉 -->
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
          <el-button type="primary" @click="$router.push(`/events/analysis?id=${detail.event_id}`)">AI 流式分析</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { dashboardApi, eventApi } from '../api/index.js'
import { ElMessage } from 'element-plus'
import { DataAnalysis, WarningFilled, AlarmClock, FirstAidKit, Document, ChatDotRound, Promotion, PieChart, List, Monitor, Warning } from '@element-plus/icons-vue'

const metrics = ref({})
const dailySummary = ref(null)
const events = ref([])
const heatmapData = ref([])
const sparklineEls = ref([])
const sparklineInstances = []

// 高危事件详情抽屉
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

const riskTag = (l) => ({ low: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[l] || 'info')
const statusTag = (s) => ({ new: 'danger', acknowledged: 'warning', resolved: 'success', ignored: 'info' }[s] || 'info')
const riskLabel = (l) => ({ low: '低', medium: '中', high: '高', critical: '严重' }[l] || l)

const showEventDetail = async (e) => {
  if (!e || !e.event_id) return
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const r = await eventApi.get(e.event_id)
    detail.value = r.data
  } catch (err) {
    ElMessage.error('加载事件详情失败')
    console.error(err)
  } finally {
    detailLoading.value = false
  }
}

const formatRawLog = (raw) => {
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

const formatAiReport = (report) => {
  if (!report) return ''
  if (typeof report === 'string') {
    try {
      return JSON.stringify(JSON.parse(report), null, 2)
    } catch {
      return report
    }
  }
  return JSON.stringify(report, null, 2)
}

// 规则颜色
const RULE_COLORS = {
  dangerous_command: '#f56c6c', command_monitor: '#e6a23c',
  severity_filter: '#409eff', http_status_alert: '#67c23a',
  response_time_alert: '#909399', keyword_match: '#b37feb',
  metric_threshold: '#36cfc9', ai_analysis_trigger: '#ff85c0',
  ai_inspection: '#597ef7',
}
const getRuleColor = (type, alpha) => {
  const c = RULE_COLORS[type] || '#909399'
  return alpha < 1 ? c + Math.round(alpha * 255).toString(16).padStart(2, '0') : c
}
const getRuleIcon = (type) => {
  const map = {
    dangerous_command: Warning, command_monitor: List,
    severity_filter: WarningFilled, http_status_alert: DataAnalysis,
    response_time_alert: AlarmClock, keyword_match: Document,
    metric_threshold: PieChart, ai_analysis_trigger: ChatDotRound,
    ai_inspection: Monitor,
  }
  return map[type] || List
}

// 热力图颜色
const heatColor = (count, total) => {
  if (!total || !count) return '#f5f7fa'
  const ratio = count / total
  if (ratio >= 0.6) return '#f56c6c'
  if (ratio >= 0.4) return '#e6a23c'
  if (ratio >= 0.2) return '#ffd666'
  return '#b7eb8f'
}

// 指标卡片
const getScoreStatus = (score) => {
  if (score == null) return { text: '暂无', color: '#c0c4cc' }
  if (score >= 90) return { text: '优秀', color: '#67c23a' }
  if (score >= 70) return { text: '良好', color: '#409eff' }
  if (score >= 50) return { text: '一般', color: '#e6a23c' }
  return { text: '较差', color: '#f56c6c' }
}
const getAbnormalStatus = (v) => {
  if (v === 0) return { text: '正常', color: '#67c23a' }
  if (v < 50) return { text: '注意', color: '#e6a23c' }
  if (v < 200) return { text: '偏高', color: '#f56c6c' }
  return { text: '严重', color: '#cf1322' }
}
const getPendingStatus = (v) => {
  if (v === 0) return { text: '已清零', color: '#67c23a' }
  if (v < 20) return { text: '正常', color: '#409eff' }
  if (v < 100) return { text: '待处理', color: '#e6a23c' }
  return { text: '积压', color: '#f56c6c' }
}

const metricCards = computed(() => {
  const m = metrics.value || {}
  const score = m.ai_score
  const ss = getScoreStatus(score)
  const as = getAbnormalStatus(m.today_abnormal_events)
  const ps = getPendingStatus(m.pending_events)
  const rs = getRecoveredStatus(m.auto_recovered_events)
  return [
    {
      key: 'ai_score', label: 'AI综合评分',
      value: score == null ? '—' : score, unit: score != null ? '/100' : '',
      icon: DataAnalysis, color: '#409eff', bg: '#ecf5ff',
      statusText: ss.text, statusColor: ss.color,
      trend: m.ai_score_trend || [], sub: '',
    },
    {
      key: 'today_abnormal', label: '异常事件总数',
      value: m.today_abnormal_events || 0, unit: '个',
      icon: WarningFilled, color: '#f56c6c', bg: '#fef0f0',
      statusText: as.text, statusColor: as.color,
      trend: m.abnormal_trend || [],
      sub: `近7天 ${m.today_abnormal_events_delta || 0} 起`,
    },
    {
      key: 'pending', label: '待处理事件',
      value: m.pending_events || 0, unit: '个',
      icon: AlarmClock, color: '#e6a23c', bg: '#fdf6ec',
      statusText: ps.text, statusColor: ps.color,
      trend: m.pending_trend || [],
      sub: `高危 ${m.pending_events_delta || 0} 起`,
    },
    {
      key: 'recovered', label: '已恢复事件',
      value: m.auto_recovered_events || 0, unit: '次',
      icon: FirstAidKit, color: '#67c23a', bg: '#f0f9eb',
      statusText: rs.text, statusColor: rs.color,
      trend: m.recovered_trend || [], sub: '',
    },
  ]
})

function getRecoveredStatus(v) {
  if (v === 0) return { text: '暂无', color: '#c0c4cc' }
  if (v < 10) return { text: '正常', color: '#67c23a' }
  if (v < 50) return { text: '良好', color: '#409eff' }
  return { text: '优秀', color: '#67c23a' }
}

// 迷你折线图（sparkline）
const renderSparklines = () => {
  sparklineInstances.forEach(c => c?.dispose())
  sparklineInstances.length = 0
  metricCards.value.forEach((item, idx) => {
    const el = sparklineEls.value[idx]
    if (!el || !item.trend || !item.trend.length) return
    const chart = echarts.init(el)
    chart.setOption({
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'category', show: false, data: item.trend.map((_, i) => i) },
      yAxis: { type: 'value', show: false, min: 0 },
      series: [{ type: 'line', smooth: true, showSymbol: false, lineStyle: { width: 1.5, color: item.color }, areaStyle: { color: item.bg }, data: item.trend }],
    })
    sparklineInstances.push(chart)
  })
}

// 告警趋势（线型图）
const trendChart = ref(null)
let chartInstance = null
const trendLoading = ref(false)
const trendTotal = ref(0)
const dateRange = ref('7')
const dateRange0 = ref([])
const granularity = ref('day')

const presetOptions = computed(() => {
  if (granularity.value === 'hour') {
    return [{ value: '1', label: '今日' }, { value: '3', label: '近3天' }, { value: '7', label: '近7天' }]
  }
  return [{ value: '7', label: '近7天' }, { value: '14', label: '近14天' }, { value: '30', label: '近30天' }]
})

const buildPreset = (days) => {
  const end = new Date(); const start = new Date()
  start.setDate(end.getDate() - (days - 1))
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return [fmt(start), fmt(end)]
}

const onGranularityChange = () => {
  const first = presetOptions.value[0]
  dateRange.value = first.value
  dateRange0.value = buildPreset(Number(first.value))
  loadTrend()
}

const onPresetChange = (val) => {
  if (val !== 'custom') { dateRange0.value = buildPreset(Number(val)); loadTrend() }
}

const renderChart = (items) => {
  if (!trendChart.value) return
  if (!chartInstance) chartInstance = echarts.init(trendChart.value)
  const dates = items.map(i => i.date.slice(5))
  const allTypes = [...new Set(items.flatMap(i => Object.keys(i.by_type || {})))]
  const typeLabels = {
    dangerous_command: '危险命令', command_monitor: '命令监控',
    severity_filter: '日志级别', http_status_alert: 'HTTP状态',
    response_time_alert: '响应时间', keyword_match: '关键字',
    metric_threshold: '指标阈值', ai_analysis_trigger: 'AI分析',
    ai_inspection: 'AI巡检',
  }
  const typeColors = {
    dangerous_command: '#f56c6c', command_monitor: '#e6a23c',
    severity_filter: '#409eff', http_status_alert: '#67c23a',
    response_time_alert: '#909399', keyword_match: '#b37feb',
    metric_threshold: '#36cfc9', ai_analysis_trigger: '#ff85c0',
    ai_inspection: '#597ef7',
  }
  const legendNames = allTypes.map(t => typeLabels[t] || t)
  const series = allTypes.map(t => ({
    name: typeLabels[t] || t,
    type: 'line',
    smooth: true,
    showSymbol: true,
    symbolSize: 6,
    lineStyle: { width: 2 },
    itemStyle: { color: typeColors[t] || undefined },
    emphasis: { focus: 'series' },
    data: items.map(i => (i.by_type || {})[t] || 0),
  }))
  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        let html = `${params[0].axisValue}<br/>`
        let total = 0
        params.forEach(p => { if (p.value > 0) { html += `${p.marker} ${p.seriesName}: ${p.value}<br/>`; total += p.value } })
        html += `<b>合计: ${total}</b>`
        return html
      },
    },
    legend: { data: legendNames, top: 0 },
    grid: { left: 40, right: 20, top: 40, bottom: 50 },
    dataZoom: [{ type: 'slider', start: 0, end: 100, height: 18 }, { type: 'inside' }],
    xAxis: { type: 'category', data: dates, axisLabel: { rotate: dates.length > 15 ? 45 : 0, hideOverlap: true } },
    yAxis: { type: 'value', minInterval: 1 },
    series,
  }, true)
}

const loadTrend = async () => {
  if (!dateRange0.value || dateRange0.value.length !== 2) return
  trendLoading.value = true
  try {
    const [start, end] = dateRange0.value
    const res = await dashboardApi.getAlertTrend({ start_date: start, end_date: end, granularity: granularity.value })
    const items = res.data?.items || []
    trendTotal.value = res.data?.total || 0
    await nextTick()
    renderChart(items)
  } catch (e) { console.error('趋势加载失败', e) }
  finally { trendLoading.value = false }
}

const loadBase = async () => {
  try {
    const [mr, sr, er, hr] = await Promise.all([
      dashboardApi.getOperationMetrics(),
      dashboardApi.getDailySummary(),
      dashboardApi.getRecentEvents(10),
      dashboardApi.getRiskHeatmap(),
    ])
    metrics.value = mr.data || {}
    dailySummary.value = sr.data || null
    events.value = (er.data?.items || []).map(e => ({ ...e, time: (e.last_seen || '').substring(0, 19) }))
    heatmapData.value = hr.data?.items || []
  } catch (e) { console.error(e) }
}

const handleResize = () => {
  chartInstance && chartInstance.resize()
  sparklineInstances.forEach(c => c?.resize())
}

onMounted(async () => {
  dateRange0.value = buildPreset(7)
  await loadBase()
  await nextTick()
  renderSparklines()
  await loadTrend()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance && chartInstance.dispose()
  chartInstance = null
  sparklineInstances.forEach(c => c?.dispose())
  sparklineInstances.length = 0
})
</script>

<style scoped>
.aiops-center { padding: 4px; }
.page-title { margin: 0 0 20px; font-size: 20px; color: #303133; }

/* === 指标卡片：参考图片三段式布局 === */
.metric-card :deep(.el-card__body) {
  padding: 16px 12px 12px;
  text-align: center;
}
.metric-top {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.metric-icon {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
}
.metric-status {
  font-size: 12px; padding: 2px 10px; border-radius: 12px;
  font-weight: 500; white-space: nowrap;
}
.metric-value-wrap {
  display: flex; align-items: baseline; justify-content: center; gap: 2px;
  margin-bottom: 4px;
}
.metric-value { font-size: 32px; font-weight: bold; color: #303133; line-height: 1.2; }
.metric-unit { font-size: 14px; color: #909399; font-weight: normal; }
.metric-label { font-size: 13px; color: #909399; margin-bottom: 8px; }
.sparkline-wrap { margin-bottom: 6px; }
.sparkline { width: 100%; height: 40px; }
.metric-sub { font-size: 12px; color: #909399; }

/* === 等高卡片 === */
.full-height-card { height: 100%; }
.full-height-card :deep(.el-card__body) { height: calc(100% - 56px); overflow-y: auto; }

/* === AI报告：左规则 + 右高危 === */
.daily-summary { padding: 4px; }
.summary-text { font-size: 14px; color: #303133; line-height: 1.8; margin-bottom: 16px; }
.report-split { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.report-left, .report-right { min-width: 0; }
.section-title { font-size: 13px; color: #909399; margin-bottom: 10px; font-weight: 500; }

/* 监控规则图标网格 */
.rules-icon-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.rule-icon-item {
  display: flex; flex-direction: column; align-items: center;
  padding: 10px 4px; border-radius: 8px; border: 1px solid #ebeef5;
  transition: all .2s; cursor: pointer;
}
.rule-icon-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); transform: translateY(-1px); }
.rule-icon-circle {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 6px; font-size: 18px;
}
.rule-icon-name { font-size: 12px; color: #606266; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.rule-icon-count { font-size: 11px; color: #909399; margin-top: 2px; }

/* 高危事件列表 */
.high-risk-list { max-height: 260px; overflow-y: auto; }
.high-risk-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f5f7fa; font-size: 13px; cursor: pointer; transition: background .2s; }
.high-risk-item:hover { background: #f5f7fa; }
.high-risk-item:hover .high-risk-summary { color: #409eff; }
.high-risk-item:last-child { border-bottom: none; }
.high-risk-summary { flex: 1; color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.high-risk-time { flex-shrink: 0; color: #c0c4cc; font-size: 12px; }

/* 事件详情抽屉 */
.detail-body { padding: 0 0 20px 0; }
.detail-section { margin-top: 20px; }
.detail-label { font-weight: 600; margin-bottom: 8px; color: var(--el-text-color-primary); }
.detail-content { background: var(--el-fill-color-light); padding: 12px; border-radius: 4px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.detail-code { background: var(--el-fill-color-light); padding: 12px; border-radius: 4px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; margin: 0; font-family: Consolas, Monaco, monospace; font-size: 13px; }

/* === 风险热力图 === */
.heatmap-wrap { display: flex; flex-direction: column; gap: 8px; }
.heatmap-row {
  display: grid; grid-template-columns: 60px 1fr 48px; align-items: center; gap: 8px;
  padding: 6px 0; border-bottom: 1px solid #f5f7fa;
}
.heatmap-row:last-child { border-bottom: none; }
.heatmap-domain { font-size: 13px; color: #303133; font-weight: 500; text-align: right; }
.heatmap-cells { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.hm-cell {
  padding: 6px 4px; border-radius: 4px; text-align: center;
  font-size: 12px; color: #606266; background: #f5f7fa;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.heatmap-total { font-size: 12px; color: #909399; text-align: center; }

/* === 快捷入口 === */
.quick-entry-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; height: 100%; align-content: center; }
.quick-entry-item {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 16px 8px; border-radius: 8px; border: 1px solid #ebeef5;
  cursor: pointer; transition: all .2s; background: #fff;
}
.quick-entry-item:hover { box-shadow: 0 2px 12px rgba(0,0,0,.1); transform: translateY(-2px); border-color: #c6e2ff; }
.quick-entry-item span { font-size: 13px; color: #606266; }

/* === 等高对齐 === */
.align-row { align-items: stretch; }
.align-row > .el-col { display: flex; }
.align-row > .el-col > .el-card { flex: 1; }
</style>
