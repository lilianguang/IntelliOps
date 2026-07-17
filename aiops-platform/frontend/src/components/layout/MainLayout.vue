<template>
  <el-container style="min-height:100vh">
    <el-aside :width="isCollapse ? '64px' : '220px'" class="sidebar" style="transition:width .3s">
      <div class="logo">
        <el-icon :size="22" class="logo-icon"><Cloudy /></el-icon>
        <span v-show="!isCollapse">AIOPS 运维平台</span>
      </div>
      <el-menu :default-active="route.path" router :collapse="isCollapse" background-color="#304156" text-color="#bfcbd9" active-text-color="#409eff">
        <el-menu-item index="/aiops-center"><el-icon><DataAnalysis /></el-icon><span>AI运营中心</span></el-menu-item>

        <el-sub-menu index="ai-center"><template #title><el-icon><MagicStick /></el-icon><span>AI智能中心</span></template>
          <el-menu-item index="/ai-center/assistant"><el-icon><ChatDotRound /></el-icon>AI助手</el-menu-item>
          <el-menu-item index="/ai-center/reports"><el-icon><Document /></el-icon>AI报告</el-menu-item>
          <el-menu-item index="/ai-center/prediction"><el-icon><TrendCharts /></el-icon>AI预测</el-menu-item>
          <el-menu-item index="/ai-center/diagnosis"><el-icon><Monitor /></el-icon>AI诊断</el-menu-item>
          <el-menu-item index="/admin/skills"><el-icon><Cpu /></el-icon>AI技能</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="events"><template #title><el-icon><WarningFilled /></el-icon><span>事件中心</span></template>
          <el-menu-item index="/events/realtime"><el-icon><Clock /></el-icon>实时事件</el-menu-item>
          <el-menu-item index="/events/history"><el-icon><Calendar /></el-icon>历史事件</el-menu-item>
          <el-menu-item index="/events/analysis"><el-icon><Cpu /></el-icon>事件分析</el-menu-item>
          <el-menu-item index="/events/statistics"><el-icon><PieChart /></el-icon>事件统计</el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/netinsight"><el-icon><Promotion /></el-icon><span>网络洞察</span></el-menu-item>

        <el-sub-menu index="resources"><template #title><el-icon><OfficeBuilding /></el-icon><span>资源中心</span></template>
          <el-sub-menu index="basic-layer"><template #title><el-icon><Folder /></el-icon>基础资源</template>
            <el-menu-item index="/admin/cmdb"><el-icon><Box /></el-icon>资产管理</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="logical-layer"><template #title><el-icon><Share /></el-icon>逻辑资源</template>
            <el-menu-item index="/admin/logical/ip-mapping"><el-icon><Connection /></el-icon>地址映射</el-menu-item>
            <el-menu-item index="/admin/logical/lb"><el-icon><Link /></el-icon>负载均衡</el-menu-item>
            <el-menu-item index="/admin/logical/interfaces"><el-icon><Postcard /></el-icon>接口信息</el-menu-item>
            <el-menu-item index="/admin/logical/ips"><el-icon><Location /></el-icon>IP地址</el-menu-item>
          </el-sub-menu>
        </el-sub-menu>

        <el-sub-menu index="admin"><template #title><el-icon><Setting /></el-icon><span>配置中心</span></template>
          <el-menu-item index="/admin/rules"><el-icon><List /></el-icon>规则配置</el-menu-item>
          <el-menu-item index="/admin/skills"><el-icon><Monitor /></el-icon>技能管理</el-menu-item>
          <el-menu-item index="/admin/datasources"><el-icon><Connection /></el-icon>数据源</el-menu-item>
          <el-menu-item index="/admin/llm"><el-icon><Cpu /></el-icon>大模型</el-menu-item>
          <el-menu-item index="/admin/alerts"><el-icon><Bell /></el-icon>告警渠道</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="system"><template #title><el-icon><Tools /></el-icon><span>系统管理</span></template>
          <el-menu-item index="/admin/users"><el-icon><UserFilled /></el-icon>用户管理</el-menu-item>
          <el-menu-item index="/admin/system/site"><el-icon><Picture /></el-icon>站点 Logo 和图标</el-menu-item>
          <el-menu-item index="/admin/system/theme"><el-icon><Brush /></el-icon>主题 / 底色配置</el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/knowledge"><el-icon><Collection /></el-icon><span>AI知识库</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #e6e6e6;display:flex;align-items:center;justify-content:space-between">
        <el-button :icon="Fold" text @click="isCollapse=!isCollapse" />
        <div><el-tag type="info" size="small">{{ user?.role }}</el-tag> {{ user?.username }} <el-button text type="primary" @click="logout">退出</el-button></div>
      </el-header>
      <el-main class="main-content"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Fold, Cloudy, DataAnalysis, MagicStick, ChatDotRound, Document, TrendCharts, Monitor, Cpu,
  WarningFilled, Clock, Calendar, PieChart, Promotion, OfficeBuilding, Folder, Box, Share, Link,
  Connection, Postcard, Location, Setting, List, Bell, UserFilled, Collection, Tools, Picture, Brush
} from '@element-plus/icons-vue'

const router = useRouter(); const route = useRoute()
const isCollapse = ref(false)
const user = computed(() => JSON.parse(localStorage.getItem('user') || '{}'))
const logout = () => { localStorage.clear(); router.push('/login') }

const applySidebarColor = (theme) => {
  if (theme?.sidebarColor) {
    document.documentElement.style.setProperty('--app-sidebar-color', theme.sidebarColor)
  }
}

onMounted(() => {
  window.addEventListener('theme-updated', (e) => applySidebarColor(e.detail))
})

onBeforeUnmount(() => {
  window.removeEventListener('theme-updated', applySidebarColor)
})
</script>

<style scoped>
.logo { height:60px; display:flex; align-items:center; justify-content:center; gap:8px; color:#fff; font-size:16px; font-weight:bold; overflow:hidden; white-space:nowrap; }
.logo-icon { flex-shrink:0; }
.sidebar { background: var(--app-sidebar-color, #304156); }
.main-content { background: var(--app-background-color, #f0f2f5); }
</style>
