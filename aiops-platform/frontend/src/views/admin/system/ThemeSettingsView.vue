<template>
  <div class="theme-settings-page">
    <div class="page-header">
      <h2 class="page-title">主题 / 底色配置</h2>
      <el-button text @click="$router.push('/admin/system')">返回系统管理</el-button>
    </div>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="24" :md="24" :lg="16">
        <el-card>
          <template #header>主题颜色配置</template>
          <el-form :model="form" label-width="120px" v-loading="loading">
            <el-form-item label="主色调">
              <div style="display:flex;align-items:center;gap:12px">
                <el-color-picker v-model="form.primaryColor" show-alpha />
                <el-input v-model="form.primaryColor" style="width:150px" />
              </div>
            </el-form-item>
            <el-form-item label="页面背景色">
              <div style="display:flex;align-items:center;gap:12px">
                <el-color-picker v-model="form.backgroundColor" show-alpha />
                <el-input v-model="form.backgroundColor" style="width:150px" />
              </div>
            </el-form-item>
            <el-form-item label="侧边栏颜色">
              <div style="display:flex;align-items:center;gap:12px">
                <el-color-picker v-model="form.sidebarColor" show-alpha />
                <el-input v-model="form.sidebarColor" style="width:150px" />
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="save" :loading="saving">保存</el-button>
              <el-button @click="reset">重置</el-button>
              <el-button text @click="restoreDefault">恢复默认</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="24" :md="24" :lg="8">
        <el-card>
          <template #header>实时预览</template>
          <div class="preview-frame" :style="{ background: form.backgroundColor }">
            <div class="preview-sidebar" :style="{ background: form.sidebarColor }">
              <div class="preview-logo-area">AIOPS</div>
              <div class="preview-menu-item">菜单项 1</div>
              <div class="preview-menu-item">菜单项 2</div>
            </div>
            <div class="preview-main">
              <div class="preview-header">
                <el-button :color="form.primaryColor" type="primary" size="small">主按钮</el-button>
                <el-button size="small">默认按钮</el-button>
              </div>
              <div class="preview-card">
                <div class="preview-card-title">示例卡片</div>
                <div class="preview-card-body">内容区域</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { systemApi } from '../../../api/index.js'
import { ElMessage } from 'element-plus'

const DEFAULT_THEME = {
  primaryColor: '#409eff',
  backgroundColor: '#f0f2f5',
  sidebarColor: '#304156',
}

const loading = ref(false)
const saving = ref(false)

const form = ref({ ...DEFAULT_THEME })

const load = async () => {
  loading.value = true
  try {
    const r = await systemApi.getSettings()
    const theme = r.data.theme || {}
    form.value = {
      primaryColor: theme.primaryColor || DEFAULT_THEME.primaryColor,
      backgroundColor: theme.backgroundColor || DEFAULT_THEME.backgroundColor,
      sidebarColor: theme.sidebarColor || DEFAULT_THEME.sidebarColor,
    }
  } catch (e) {
    ElMessage.error('加载主题配置失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    await systemApi.updateSettings({ theme: form.value })
    ElMessage.success('保存成功')
    applyTheme(form.value)
  } catch (e) {
    ElMessage.error('保存失败')
    console.error(e)
  } finally {
    saving.value = false
  }
}

const reset = () => {
  load()
}

const restoreDefault = () => {
  form.value = { ...DEFAULT_THEME }
}

const applyTheme = (theme) => {
  const root = document.documentElement
  if (theme.primaryColor) {
    root.style.setProperty('--el-color-primary', theme.primaryColor)
  }
  if (theme.backgroundColor) {
    root.style.setProperty('--app-background-color', theme.backgroundColor)
  }
  if (theme.sidebarColor) {
    root.style.setProperty('--app-sidebar-color', theme.sidebarColor)
  }
  window.dispatchEvent(new CustomEvent('theme-updated', { detail: theme }))
}

watch(form, (theme) => {
  applyTheme(theme)
}, { deep: true })

onMounted(() => {
  load()
})
</script>

<style scoped>
.theme-settings-page { padding: 4px; }
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  white-space: nowrap;
}
.preview-frame {
  display: flex;
  height: 260px;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}
.preview-sidebar {
  width: 120px;
  color: #bfcbd9;
  padding: 12px;
  font-size: 12px;
}
.preview-logo-area {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.preview-menu-item {
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 8px;
  background: rgba(255,255,255,0.05);
}
.preview-main {
  flex: 1;
  padding: 12px;
}
.preview-header {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.preview-card {
  background: #fff;
  border-radius: 4px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.preview-card-title {
  font-weight: bold;
  margin-bottom: 8px;
  color: #303133;
}
.preview-card-body {
  color: #606266;
  font-size: 13px;
}
</style>
