<template>
  <div class="events-statistics-page">
    <h2>事件统计</h2>

    <!-- 顶部指标 -->
    <el-row :gutter="16" style="margin-bottom:20px">
      <el-col :span="4" v-for="item in summaryCards" :key="item.label">
        <el-card shadow="hover">
          <div class="stat-value" :style="{ color: item.color }">{{ item.value }}</div>
          <div class="stat-label">{{ item.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 -->
    <el-card style="margin-bottom:20px">
      <template #header>事件趋势（最近 7 天）</template>
      <div ref="trendChart" style="width:100%;height:300px"></div>
    </el-card>

    <el-row :gutter="20" style="margin-bottom:20px">
      <el-col :span="12">
        <el-card>
          <template #header>风险等级分布</template>
          <div ref="riskChart" style="width:100%;height:300px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>状态分布</template>
          <div ref="statusChart" style="width:100%;height:300px"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>事件类型 TOP10</template>
          <div ref="typeChart" style="width:100%;height:320px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>设备 TOP10</template>
          <el-table :data="stats.by_device || []" stripe size="small" style="width:100%">
            <el-table-column type="index" label="排名" width="70" />
            <el-table-column prop="name" label="设备" />
            <el-table-column prop="count" label="事件数" width="100" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { eventApi } from '../../api/index.js'

const stats = ref({})
const trendChart = ref(null)
const riskChart = ref(null)
const statusChart = ref(null)
const typeChart = ref(null)
let charts = {}

const summaryCards = computed(() => {
  const s = stats.value || {}
  const br = s.by_risk || {}
  return [
    { label: '事件总数', value: s.total || 0, color: '#409eff' },
    { label: '严重', value: br.critical || 0, color: '#f56c6c' },
    { label: '高', value: br.high || 0, color: '#e6a23c' },
    { label: '中', value: br.medium || 0, color: '#67c23a' },
    { label: '低', value: br.low || 0, color: '#909399' },
  ]
})

const renderTrend = () => {
  if (!trendChart.value) return
  const data = stats.value.trend || []
  charts.trend = echarts.init(trendChart.value)
  charts.trend.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: data.map(i => i.date) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      data: data.map(i => i.count),
      type: 'line',
      smooth: true,
      areaStyle: { opacity: 0.15 },
      itemStyle: { color: '#409eff' },
    }],
  })
}

const renderPie = (refName, data, title) => {
  if (!charts[refName]) charts[refName] = echarts.init(refName === 'risk' ? riskChart.value : statusChart.value)
  const colorMap = refName === 'risk'
    ? { critical: '#f56c6c', high: '#e6a23c', medium: '#67c23a', low: '#909399' }
    : { new: '#f56c6c', acknowledged: '#e6a23c', resolved: '#67c23a', ignored: '#909399' }
  const seriesData = Object.entries(data || {}).map(([k, v]) => ({ name: k, value: v, itemStyle: { color: colorMap[k] } }))
  charts[refName].setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: seriesData,
      label: { formatter: '{b}: {c}' },
    }],
  })
}

const renderTypeChart = () => {
  if (!typeChart.value) return
  const data = stats.value.by_type || []
  charts.type = echarts.init(typeChart.value)
  charts.type.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 20, top: 10, bottom: 20 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: data.map(i => i.name).reverse() },
    series: [{
      type: 'bar',
      data: data.map(i => i.count).reverse(),
      itemStyle: { color: '#409eff', borderRadius: [0, 4, 4, 0] },
    }],
  })
}

const load = async () => {
  try {
    const r = await eventApi.getStats()
    stats.value = r.data || {}
    await nextTick()
    renderTrend()
    renderPie('risk', stats.value.by_risk)
    renderPie('status', stats.value.by_status)
    renderTypeChart()
  } catch (e) {
    console.error('加载事件统计失败', e)
  }
}

const handleResize = () => {
  Object.values(charts).forEach(c => c && c.resize())
}

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  Object.values(charts).forEach(c => c && c.dispose())
  charts = {}
})
</script>

<style scoped>
.events-statistics-page { padding: 4px; }
.stat-value { font-size: 28px; font-weight: bold; text-align: center; }
.stat-label { text-align: center; color: #909399; margin-top: 6px; font-size: 13px; }
</style>
