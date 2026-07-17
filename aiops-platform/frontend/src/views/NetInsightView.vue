<template>
  <div style="display:flex;flex-direction:column;gap:12px;height:calc(100vh - 120px)">
    <!-- 上半部分：配置概览 -->
    <el-card body-style="padding:0;overflow:hidden;display:flex;flex-direction:column" style="min-height:280px;max-height:45%">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
          <span style="font-weight:600">配置备份概览</span>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <el-select v-model="vendorFilter" placeholder="全部厂商" clearable size="small" style="width:130px" @change="loadConfigs">
              <el-option v-for="v in vendors" :key="v" :label="v" :value="v" />
            </el-select>
            <el-input v-model="regionFilter" placeholder="区域筛选" clearable size="small" style="width:120px" @keyup.enter="loadConfigs" />
            <el-input v-model="nameFilter" placeholder="名称筛选" clearable size="small" style="width:140px" @keyup.enter="loadConfigs" />
            <el-button size="small" @click="loadConfigs">查询</el-button>
            <el-button size="small" @click="resetFilters">重置</el-button>
            <el-button size="small" type="primary" :loading="scanning" @click="doScan">
              <el-icon style="margin-right:4px"><Refresh /></el-icon>扫描目录
            </el-button>
            <el-button size="small" @click="uploadDialogVisible = true">上传配置</el-button>
            <el-button size="small" @click="settingsDialogVisible = true">设置</el-button>
          </div>
        </div>
      </template>
      <el-table :data="configs" size="small" stripe style="flex:1;overflow:auto" max-height="100%"
                v-loading="loadingConfigs" empty-text="暂无配置，请先扫描目录或上传">
        <el-table-column type="selection" width="40" align="center" />
        <el-table-column prop="vendor" label="厂商" width="100" align="center">
          <template #default="{row}">
            <el-tag :type="vendorTagType(row.vendor)" size="small">{{ row.vendor }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="140" align="center" />
        <el-table-column prop="name" label="名称" width="150" show-overflow-tooltip />
        <el-table-column prop="region" label="区域" width="120" align="center" />
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="file_size" label="大小" width="90" align="center">
          <template #default="{row}">{{ humanSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="file_date" label="配置日期" width="120" align="center" />
        <el-table-column prop="updated_at" label="更新时间" width="160" align="center">
          <template #default="{row}">{{ (row.updated_at || '').substring(0, 19).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{row}">
            <el-button size="small" text type="primary" @click="openViewer(row)">查看</el-button>
            <el-button size="small" text type="warning" @click="openVersions(row)">版本</el-button>
            <el-button size="small" text type="danger" @click="deleteRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 下半部分：AI 问答 -->
    <el-card body-style="flex:1;display:flex;flex-direction:column;overflow:hidden;padding:0" style="flex:1;display:flex;flex-direction:column;min-height:0">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-weight:600">AI 配置问答</span>
          <div style="display:flex;gap:8px;align-items:center">
            <el-checkbox v-model="useSelected" size="small">仅分析勾选设备</el-checkbox>
            <el-button size="small" @click="clearChat">清空对话</el-button>
          </div>
        </div>
      </template>

      <!-- 消息列表 -->
      <div ref="msgBox" style="flex:1;overflow-y:auto;padding:16px;background:#fafafa">
        <div v-for="(msg, i) in messages" :key="i" style="margin-bottom:16px">
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" style="display:flex;justify-content:flex-end">
            <div style="background:#409eff;color:#fff;padding:10px 14px;border-radius:12px 12px 2px 12px;max-width:70%;white-space:pre-wrap">{{ msg.content }}</div>
          </div>
          <!-- AI 消息 -->
          <div v-else>
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
              <el-tag size="small" type="success">AI</el-tag>
              <span v-if="msg.meta" style="font-size:12px;color:#909399">
                分析 {{ msg.meta.config_count }} 台设备 ({{ (msg.meta.vendors || []).join(', ') }})
              </span>
            </div>
            <div class="ai-bubble markdown-body" v-html="renderMd(msg.content)"></div>
          </div>
        </div>
        <!-- 加载指示 -->
        <div v-if="streaming && !currentAiContent" style="padding:8px 0;color:#909399">
          <el-icon class="is-loading" style="margin-right:4px"><Loading /></el-icon>正在分析配置...
        </div>
      </div>

      <!-- 输入区域 -->
      <div style="padding:12px;border-top:1px solid #eee;display:flex;gap:8px">
        <el-input v-model="question" placeholder="输入你的问题，如：211.147.153.2 映射的内部IP是什么？"
                  :disabled="streaming" @keyup.enter="doAsk">
          <template #prepend>
            <el-select v-model="askVendor" placeholder="全部" style="width:100px" clearable>
              <el-option v-for="v in vendors" :key="v" :label="v" :value="v" />
            </el-select>
          </template>
        </el-input>
        <el-button type="primary" :disabled="streaming || !question.trim()" @click="doAsk">
          {{ streaming ? '生成中...' : '提问' }}
        </el-button>
        <el-button v-if="streaming" type="danger" plain @click="stopStream">停止</el-button>
      </div>
    </el-card>

    <!-- 配置查看弹窗 -->
    <el-dialog v-model="viewerVisible" :title="viewerTitle" width="800px" destroy-on-close>
      <div style="max-height:60vh;overflow:auto;background:#f5f7fa;padding:12px;border-radius:6px">
        <pre style="margin:0;white-space:pre-wrap;word-break:break-all;font-family:Consolas,monospace;font-size:13px">{{ viewerContent }}</pre>
      </div>
      <template #footer>
        <el-button @click="viewerVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyContent">复制</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史弹窗 -->
    <el-dialog v-model="versionsVisible" :title="versionsTitle" width="700px" destroy-on-close>
      <el-table :data="versions" size="small" stripe empty-text="暂无版本记录">
        <el-table-column prop="time" label="提交时间" width="160" />
        <el-table-column prop="message" label="提交说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="120" align="center">
          <template #default="{row}">
            <el-button size="small" text type="primary" @click="viewVersion(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 历史版本内容弹窗 -->
    <el-dialog v-model="versionContentVisible" title="历史版本内容" width="800px" destroy-on-close>
      <div style="max-height:50vh;overflow:auto;background:#f5f7fa;padding:12px;border-radius:6px">
        <pre style="margin:0;white-space:pre-wrap;word-break:break-all;font-family:Consolas,monospace;font-size:13px">{{ versionContent }}</pre>
      </div>
      <template #footer><el-button @click="versionContentVisible = false">关闭</el-button></template>
    </el-dialog>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadDialogVisible" title="上传配置文件" width="480px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="厂商">
          <el-select v-model="uploadVendor" placeholder="选择厂商" style="width:100%">
            <el-option v-for="v in vendorOptions" :key="v.value" :label="v.label" :value="v.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备IP">
          <el-input v-model="uploadIp" placeholder="如文件名已包含IP可留空" />
          <div style="color:#909399;font-size:12px">若文件名不是 IP.cfg / IP_running_日期.cfg 格式，请填写设备IP</div>
        </el-form-item>
        <el-form-item label="配置文件">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" accept=".cfg,.conf,.txt"
                     :on-change="onUploadChange" :on-exceed="() => ElMessage.warning('每次只能上传一个文件')">
            <el-button type="primary">选择文件</el-button>
            <template #tip><div style="color:#909399;font-size:12px">支持 .cfg / .conf / .txt 格式</div></template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 设置弹窗 -->
    <el-dialog v-model="settingsDialogVisible" title="网络洞察设置" width="500px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="配置源目录">
          <el-input v-model="settingsPath" placeholder="如 /data/net_configs_source" clearable />
          <div style="font-size:12px;color:#909399;margin-top:4px;line-height:1.6">
            扫描/同步的<strong>源目录</strong>，此处填<strong>容器内路径</strong>（默认 <code>/data/net_configs_source</code>，
            对应宿主机项目下的 <code>data/net_configs_source</code> 目录）。修改后点【扫描】即按新目录同步。
            也可直接用上方「上传」按钮导入配置，无需依赖此目录。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="settingsDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingSettings" @click="saveSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import { netinsightApi } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Loading } from '@element-plus/icons-vue'

// ---- markdown-it ----
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const renderMd = (text) => md.render(text || '')

// ---- 配置管理状态 ----
const configs = ref([])
const vendors = ref([])
const vendorFilter = ref('')
const regionFilter = ref('')
const nameFilter = ref('')
const loadingConfigs = ref(false)
const scanning = ref(false)

const vendorOptions = [
  { value: 'h3c', label: 'H3C' },
  { value: 'huawei', label: '华为' },
  { value: 'cisco', label: 'Cisco' },
  { value: 'nsfocus', label: '绿盟' },
  { value: 'venustech', label: '启明星辰' },
  { value: 'topsec', label: '天融信' },
  { value: 'sangfor', label: '深信服' },
  { value: 'hillstone', label: '山石网科' },
  { value: 'ruijie', label: '锐捷' },
  { value: 'juniper', label: 'Juniper' },
  { value: 'fortinet', label: 'Fortinet' },
]

const vendorTagType = (v) => {
  const map = { h3c: 'success', huawei: '', cisco: 'warning', nsfocus: 'danger', venustech: 'info' }
  return map[v] || 'info'
}

const humanSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function loadConfigs() {
  loadingConfigs.value = true
  try {
    const params = {}
    if (vendorFilter.value) params.vendor = vendorFilter.value
    if (regionFilter.value) params.region = regionFilter.value
    if (nameFilter.value) params.name = nameFilter.value
    const res = await netinsightApi.listConfigs(params)
    configs.value = res.data.configs || []
    vendors.value = res.data.vendors || []
  } catch (e) {
    ElMessage.error('加载配置列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loadingConfigs.value = false
  }
}

function resetFilters() {
  vendorFilter.value = ''
  regionFilter.value = ''
  nameFilter.value = ''
  loadConfigs()
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ${row.ip_address} 的配置备份？`, '提示', { type: 'warning' })
    await netinsightApi.deleteConfig(row.id)
    ElMessage.success('已删除')
    loadConfigs()
  } catch { /* 取消 */ }
}

async function doScan() {
  scanning.value = true
  try {
    const res = await netinsightApi.scan()
    const d = res.data
    ElMessage.success(`扫描完成: 共扫描 ${d.scanned} 个文件, 新增 ${d.created}, 更新 ${d.updated}`)
    await loadConfigs()
  } catch (e) {
    ElMessage.error('扫描失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    scanning.value = false
  }
}

// ---- 配置查看 ----
const viewerVisible = ref(false)
const viewerTitle = ref('')
const viewerContent = ref('')

async function openViewer(row) {
  viewerTitle.value = `${row.ip_address} - ${row.file_name}`
  viewerContent.value = '加载中...'
  viewerVisible.value = true
  try {
    const res = await netinsightApi.getContent(row.id)
    viewerContent.value = res.data.content || '无内容'
  } catch (e) {
    viewerContent.value = '加载失败: ' + (e.response?.data?.detail || e.message)
  }
}

function copyContent() {
  navigator.clipboard.writeText(viewerContent.value).then(() => ElMessage.success('已复制'))
}

// ---- 版本历史 ----
const versionsVisible = ref(false)
const versionsTitle = ref('')
const versions = ref([])
const currentVersionConfigId = ref(null)
const versionContentVisible = ref(false)
const versionContent = ref('')

async function openVersions(row) {
  versionsTitle.value = `${row.ip_address} - 版本历史`
  currentVersionConfigId.value = row.id
  versionsVisible.value = true
  try {
    const res = await netinsightApi.getVersions(row.id)
    versions.value = res.data.versions || []
  } catch (e) {
    ElMessage.error('加载版本历史失败: ' + (e.response?.data?.detail || e.message))
    versions.value = []
  }
}

async function viewVersion(row) {
  versionContent.value = '加载中...'
  versionContentVisible.value = true
  try {
    if (!currentVersionConfigId.value) {
      versionContent.value = '无法确定当前配置'
      return
    }
    const res = await netinsightApi.getVersionContent(currentVersionConfigId.value, row.commit)
    versionContent.value = res.data.content || '无内容'
  } catch (e) {
    versionContent.value = '加载失败: ' + (e.response?.data?.detail || e.message)
  }
}

// ---- 上传 ----
const uploadDialogVisible = ref(false)
const uploadVendor = ref('h3c')
const uploadIp = ref('')
const uploadFile = ref(null)
const uploading = ref(false)
const uploadRef = ref(null)

function onUploadChange(file) {
  uploadFile.value = file.raw
}

async function doUpload() {
  if (!uploadVendor.value) return ElMessage.warning('请选择厂商')
  if (!uploadFile.value) return ElMessage.warning('请选择文件')
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', uploadFile.value)
    fd.append('vendor', uploadVendor.value)
    if (uploadIp.value && uploadIp.value.trim()) {
      fd.append('ip', uploadIp.value.trim())
    }
    const res = await netinsightApi.upload(fd)
    const scan = res.data.scan || {}
    ElMessage.success(`上传成功，本次扫描 ${scan.scanned || 0} 个文件，新增 ${scan.created || 0} 条`)
    uploadDialogVisible.value = false
    uploadFile.value = null
    uploadIp.value = ''
    uploadRef.value?.clearFiles()
    await loadConfigs()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}

// ---- 设置 ----
const settingsDialogVisible = ref(false)
const settingsPath = ref('')
const savingSettings = ref(false)

async function loadSettings() {
  try {
    const res = await netinsightApi.getSettings()
    settingsPath.value = res.data.net_config_source_path || ''
  } catch { /* 忽略 */ }
}

async function saveSettings() {
  savingSettings.value = true
  try {
    await netinsightApi.updateSettings({ net_config_base_path: settingsPath.value })
    ElMessage.success('设置已保存')
    settingsDialogVisible.value = false
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingSettings.value = false
  }
}

// ---- AI 问答 ----
const messages = ref([])
const question = ref('')
const askVendor = ref('')
const streaming = ref(false)
const currentAiContent = ref('')
const useSelected = ref(false)
const msgBox = ref(null)
let streamController = null

function clearChat() {
  messages.value = []
  currentAiContent.value = ''
}

function scrollToBottom() {
  nextTick(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
  })
}

function doAsk() {
  const q = question.value.trim()
  if (!q || streaming.value) return

  // 添加用户消息
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  scrollToBottom()

  // 开始流式请求
  streaming.value = true
  currentAiContent.value = ''

  const aiMsg = { role: 'ai', content: '', meta: null }
  messages.value.push(aiMsg)

  const data = { question: q, max_tokens: 8192 }
  if (askVendor.value) data.vendor = askVendor.value
  // 将配置概览的筛选条件作为 filters 传递给后端，约束 AI 分析范围
  data.filters = {
    vendor: vendorFilter.value || undefined,
    region: regionFilter.value || undefined,
    name: nameFilter.value || undefined,
  }

  streamController = netinsightApi.streamChat(data, {
    onMeta: (meta) => {
      aiMsg.meta = meta
      scrollToBottom()
    },
    onContent: (text) => {
      currentAiContent.value += text
      aiMsg.content = currentAiContent.value
      scrollToBottom()
    },
    onFinish: () => {
      streaming.value = false
      currentAiContent.value = ''
      streamController = null
    },
    onError: (err) => {
      streaming.value = false
      currentAiContent.value = ''
      streamController = null
      aiMsg.content = aiMsg.content || `**错误**: ${err}`
      scrollToBottom()
    },
  })
}

function stopStream() {
  if (streamController) {
    streamController.abort()
    streamController = null
  }
  streaming.value = false
  currentAiContent.value = ''
}

// ---- 初始化 ----
onMounted(async () => {
  await loadSettings()
  await loadConfigs()
})
</script>

<style scoped>
.ai-bubble {
  background: #fff;
  padding: 12px 16px;
  border-radius: 2px 12px 12px 12px;
  border: 1px solid #e8e8e8;
  max-width: 90%;
  line-height: 1.7;
}
.ai-bubble :deep(pre) {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
}
.ai-bubble :deep(code) {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
}
.ai-bubble :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}
.ai-bubble :deep(th), .ai-bubble :deep(td) {
  border: 1px solid #ddd;
  padding: 4px 8px;
  font-size: 13px;
}
</style>
