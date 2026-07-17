<template>
  <div class="site-settings-page">
    <div class="page-header">
      <h2 class="page-title">站点 Logo 和图标</h2>
      <el-button text @click="$router.push('/admin/system')">返回系统管理</el-button>
    </div>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="24" :md="24" :lg="16">
        <el-card>
          <template #header>站点信息配置</template>
          <el-form :model="form" label-width="120px" v-loading="loading">
            <el-form-item label="站点名称">
              <el-input v-model="form.name" placeholder="AIOPS 运维平台" clearable />
            </el-form-item>
            <el-form-item label="站点 Logo">
              <div class="upload-field">
                <el-upload
                  :show-file-list="false"
                  :auto-upload="false"
                  accept="image/*"
                  :on-change="(f) => onPick(f, 'logo')"
                >
                  <el-button type="primary" plain :icon="UploadFilled">选择本地图片</el-button>
                </el-upload>
                <el-button v-if="form.logo" text type="danger" @click="form.logo=''">清除</el-button>
                <span class="upload-tip">支持 PNG / JPG / SVG，建议 ≤ 1MB</span>
              </div>
            </el-form-item>
            <el-form-item label="浏览器图标">
              <div class="upload-field">
                <el-upload
                  :show-file-list="false"
                  :auto-upload="false"
                  accept="image/*,.ico"
                  :on-change="(f) => onPick(f, 'favicon')"
                >
                  <el-button type="primary" plain :icon="UploadFilled">选择本地图片</el-button>
                </el-upload>
                <el-button v-if="form.favicon" text type="danger" @click="form.favicon=''">清除</el-button>
                <span class="upload-tip">支持 ICO / PNG，建议 ≤ 200KB</span>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="save" :loading="saving">保存</el-button>
              <el-button @click="reset">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="24" :md="24" :lg="8">
        <el-card>
          <template #header>实时预览</template>
          <div class="preview-block">
            <div class="preview-label">浏览器标题</div>
            <div class="preview-content">{{ form.name || 'AIOPS 运维平台' }}</div>
          </div>
          <div class="preview-block">
            <div class="preview-label">Logo</div>
            <div class="preview-content">
              <img v-if="form.logo" :src="form.logo" class="preview-logo" @error="logoError=true" />
              <div v-else class="preview-logo placeholder">未配置</div>
            </div>
          </div>
          <div class="preview-block">
            <div class="preview-label">浏览器图标</div>
            <div class="preview-content">
              <img v-if="form.favicon" :src="form.favicon" class="preview-favicon" @error="faviconError=true" />
              <div v-else class="preview-favicon placeholder">未配置</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { systemApi } from '../../../api/index.js'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

// 图片大小上限（字节）
const SIZE_LIMIT = { logo: 1024 * 1024, favicon: 200 * 1024 }

/** 选择本地图片→校验→转 base64 data URL 存入表单 */
const onPick = (uploadFile, field) => {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  const isImage = (file.type || '').startsWith('image/') || /\.(ico|png|jpe?g|svg|gif|webp)$/i.test(file.name || '')
  if (!isImage) {
    ElMessage.error('请选择图片文件')
    return
  }
  const limit = SIZE_LIMIT[field]
  if (file.size > limit) {
    ElMessage.error(`图片过大，请控制在 ${Math.round(limit / 1024)}KB 以内`)
    return
  }
  const reader = new FileReader()
  reader.onload = (e) => {
    form.value[field] = e.target.result
    if (field === 'logo') logoError.value = false
    else faviconError.value = false
  }
  reader.onerror = () => ElMessage.error('图片读取失败')
  reader.readAsDataURL(file)
}

const loading = ref(false)
const saving = ref(false)
const logoError = ref(false)
const faviconError = ref(false)

const form = ref({
  name: '',
  logo: '',
  favicon: '',
})

const load = async () => {
  loading.value = true
  try {
    const r = await systemApi.getSettings()
    const site = r.data.site || {}
    form.value = {
      name: site.name || '',
      logo: site.logo || '',
      favicon: site.favicon || '',
    }
  } catch (e) {
    ElMessage.error('加载站点配置失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    await systemApi.updateSettings({ site: form.value })
    ElMessage.success('保存成功')
    applySite(form.value)
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

const applySite = (site) => {
  if (site.name) document.title = site.name
  if (site.favicon) {
    let link = document.querySelector('link[rel="icon"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = site.favicon
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.site-settings-page { padding: 4px; }
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
.preview-block { margin-bottom: 16px; }
.upload-field {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.upload-tip {
  color: #909399;
  font-size: 12px;
}
.preview-block:last-child { margin-bottom: 0; }
.preview-label { color: #909399; font-size: 13px; margin-bottom: 8px; }
.preview-content { color: #303133; }
.preview-logo {
  max-width: 180px;
  max-height: 60px;
  object-fit: contain;
}
.preview-favicon {
  width: 32px;
  height: 32px;
  object-fit: contain;
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  color: #909399;
  font-size: 12px;
  border-radius: 4px;
}
.preview-logo.placeholder { width: 180px; height: 60px; }
.preview-favicon.placeholder { width: 32px; height: 32px; }
</style>
