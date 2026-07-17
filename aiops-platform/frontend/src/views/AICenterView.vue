<template>
  <div class="ai-center">
    <h2 class="page-title">AI 智能中心</h2>
    <p class="page-desc">基于大模型的智能运维能力入口，选择对应能力开始分析</p>
    <div class="capability-grid">
      <div v-for="cap in capabilities" :key="cap.key" class="capability-card" @click="goTo(cap)">
        <div class="cap-icon" :style="{ background: cap.bg }">
          <el-icon :size="28" :color="cap.color"><component :is="cap.icon" /></el-icon>
        </div>
        <div class="cap-info">
          <div class="cap-title">{{ cap.title }}</div>
          <div class="cap-desc">{{ cap.desc }}</div>
        </div>
        <el-icon class="cap-arrow" color="#c0c4cc" :size="18"><ArrowRight /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup>
import { markRaw } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, Document, TrendCharts, Monitor, MagicStick, ArrowRight } from '@element-plus/icons-vue'

const router = useRouter()

const capabilities = [
  { key: 'assistant', title: 'AI助手', desc: '通用 AI 对话与运维问答', icon: markRaw(ChatDotRound), color: '#409eff', bg: '#ecf5ff', path: '/ai-center/assistant' },
  { key: 'reports', title: 'AI报告', desc: '多模融合分析，生成综合运维报告', icon: markRaw(Document), color: '#409eff', bg: '#ecf5ff', path: '/ai-center/reports' },
  { key: 'prediction', title: 'AI预测', desc: '基于历史数据预测告警趋势与风险', icon: markRaw(TrendCharts), color: '#67c23a', bg: '#f0f9eb', path: '/ai-center/prediction' },
  { key: 'diagnosis', title: 'AI诊断', desc: '批量执行诊断命令，提升运维效率', icon: markRaw(Monitor), color: '#9b59b6', bg: '#f3e8ff', path: '/ai-center/diagnosis' },
  { key: 'skills', title: 'AI技能', desc: '管理和配置 AI 分析技能', icon: markRaw(MagicStick), color: '#e6a23c', bg: '#fdf6ec', path: '/admin/skills' },
]

const goTo = (cap) => {
  router.push(cap.path)
}
</script>

<style scoped>
.ai-center { padding: 20px; }
.page-title { margin: 0 0 8px; font-size: 20px; color: #303133; }
.page-desc { margin: 0 0 24px; color: #909399; font-size: 14px; }
.capability-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.capability-card {
  display: flex; align-items: center; gap: 14px;
  padding: 20px; border-radius: 8px; border: 1px solid #ebeef5;
  background: #fff; cursor: pointer; transition: all .2s;
  position: relative;
}
.capability-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,.1); transform: translateY(-2px); border-color: #c6e2ff; }
.cap-icon { width: 56px; height: 56px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.cap-info { flex: 1; min-width: 0; }
.cap-title { font-size: 16px; font-weight: 600; color: #303133; margin-bottom: 6px; }
.cap-desc { font-size: 13px; color: #909399; line-height: 1.5; }
.cap-arrow { margin-left: auto; }
</style>
