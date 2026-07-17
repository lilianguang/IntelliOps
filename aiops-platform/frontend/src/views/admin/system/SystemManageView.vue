<template>
  <div class="system-manage">
    <h2 class="page-title">系统管理</h2>
    <div class="module-grid">
      <div class="module-card" @click="$router.push('/admin/system/site')">
        <el-icon :size="28" color="#409eff"><Picture /></el-icon>
        <div class="module-info">
          <div class="module-title">站点 Logo 和图标</div>
          <div class="module-desc">配置站点名称、Logo、浏览器图标</div>
        </div>
        <el-icon class="module-arrow" color="#c0c4cc" :size="18"><ArrowRight /></el-icon>
      </div>
      <div class="module-card" @click="$router.push('/admin/system/theme')">
        <el-icon :size="28" color="#67c23a"><Brush /></el-icon>
        <div class="module-info">
          <div class="module-title">主题 / 底色配置</div>
          <div class="module-desc">配置页面背景色、主色调、侧边栏颜色</div>
        </div>
        <el-icon class="module-arrow" color="#c0c4cc" :size="18"><ArrowRight /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Picture, Brush, ArrowRight } from '@element-plus/icons-vue'
</script>

<style scoped>
.system-manage { padding: 20px; }
.page-title { margin: 0 0 24px; font-size: 20px; color: #303133; }
.module-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.module-card {
  display: flex; align-items: center; gap: 14px;
  padding: 20px; border-radius: 8px; border: 1px solid #ebeef5;
  background: #fff; cursor: pointer; transition: all .2s;
}
.module-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,.1); transform: translateY(-2px); border-color: #c6e2ff; }
.module-info { flex: 1; min-width: 0; }
.module-title { font-size: 16px; font-weight: 600; color: #303133; margin-bottom: 6px; }
.module-desc { font-size: 13px; color: #909399; }
.module-arrow { margin-left: auto; }
</style>
