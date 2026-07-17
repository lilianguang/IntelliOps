<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px"><h2>告警渠道配置</h2><el-button type="primary" @click="addAlert">新增渠道</el-button></div>
    <el-table :data="list" stripe>
      <el-table-column prop="name" label="名称" width="150" />
      <el-table-column prop="channel_type" label="类型" width="120">
        <template #default="{row}">{{ {dingtalk:'钉钉',email:'邮件',webhook:'Webhook'}[row.channel_type]||row.channel_type }}</template>
      </el-table-column>
      <el-table-column prop="config" label="配置" min-width="260">
        <template #default="{row}"><el-text truncated>{{ configPreview(row) }}</el-text></template>
      </el-table-column>
      <el-table-column label="启用" width="80"><template #default="{row}"><el-switch :model-value="!!row.enabled" @change="(v)=>toggleAlert(row,v)" /></template></el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{row}">
          <el-button text type="success" size="small" :loading="testingId===row.id" @click="testRow(row)">连通性测试</el-button>
          <el-button text type="primary" size="small" @click="editAlert(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="delAlert(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="showForm" :title="editId?'编辑告警渠道':'新增告警渠道'" width="540px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="form.channel_type" @change="onTypeChange"><el-option label="钉钉" value="dingtalk" /><el-option label="邮件" value="email" /><el-option label="Webhook" value="webhook" /></el-select></el-form-item>
        <el-form-item v-if="form.channel_type==='dingtalk'" label="Webhook URL"><el-input v-model="form.config.webhook_url" /></el-form-item>
        <el-form-item v-if="form.channel_type==='dingtalk'" label="加签密钥"><el-input v-model="form.config.secret" /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="SMTP地址"><el-input v-model="form.config.smtp_host" /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="端口"><el-input-number v-model="form.config.smtp_port" /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="账号"><el-input v-model="form.config.smtp_user" /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="密码"><el-input v-model="form.config.smtp_pass" type="password" show-password /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="发件人"><el-input v-model="form.config.from_addr" placeholder="留空则使用账号" /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="收件人"><el-input v-model="form.config.to_addrs_str" placeholder="多个用逗号分隔" /></el-form-item>
        <el-form-item v-if="form.channel_type==='email'" label="启用SSL"><el-switch v-model="form.config.use_ssl" /></el-form-item>
        <el-form-item v-if="form.channel_type==='webhook'" label="URL"><el-input v-model="form.config.url" /></el-form-item>
        <el-form-item v-if="form.channel_type==='webhook'" label="方法"><el-select v-model="form.config.method"><el-option label="POST" value="POST" /><el-option label="GET" value="GET" /></el-select></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button :loading="testing" @click="testForm">连通性测试</el-button>
        <el-button type="primary" @click="saveAlert">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { configApi } from '../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const list = ref([]); const showForm = ref(false); const editId = ref(null)
const testing = ref(false); const testingId = ref(null)
const form = ref({ name:'', channel_type:'dingtalk', config:{} })

const emptyConfig = (t) => {
  if (t === 'dingtalk') return { webhook_url:'', secret:'' }
  if (t === 'email') return { smtp_host:'', smtp_port:465, smtp_user:'', smtp_pass:'', from_addr:'', to_addrs_str:'', use_ssl:true }
  return { url:'', method:'POST', headers:{} }
}
const onTypeChange = (t) => { form.value.config = emptyConfig(t) }

// 构建/还原提交用的 config（email 的 to_addrs 转成数组）
const buildPayload = () => {
  const cfg = JSON.parse(JSON.stringify(form.value.config))
  if (form.value.channel_type === 'email') {
    cfg.to_addrs = (cfg.to_addrs_str || '').split(',').map(s => s.trim()).filter(Boolean)
    delete cfg.to_addrs_str
    if (!cfg.from_addr) cfg.from_addr = cfg.smtp_user
  }
  return { name: form.value.name, channel_type: form.value.channel_type, config: cfg }
}

const configPreview = (row) => {
  const c = row.config || {}
  if (row.channel_type === 'dingtalk') return c.webhook_url || ''
  if (row.channel_type === 'email') return `${c.smtp_user || ''}@${c.smtp_host || ''}:${c.smtp_port || ''}`
  return c.url || ''
}

const showResult = (d) => d.success ? ElMessage.success(`${d.message} (${d.latency_ms}ms)`) : ElMessage.error(d.message || '连接失败')

const load = async () => { try { const r = await configApi.listAlerts(); list.value = r.data } catch(e) { console.error(e) } }
onMounted(load)

const addAlert = () => { editId.value = null; form.value = { name:'', channel_type:'dingtalk', config: emptyConfig('dingtalk') }; showForm.value = true }
const editAlert = (row) => {
  editId.value = row.id
  const cfg = { ...emptyConfig(row.channel_type), ...(row.config || {}) }
  if (row.channel_type === 'email') cfg.to_addrs_str = Array.isArray(cfg.to_addrs) ? cfg.to_addrs.join(',') : (cfg.to_addrs || '')
  form.value = { name: row.name, channel_type: row.channel_type, config: cfg }
  showForm.value = true
}

const testForm = async () => {
  testing.value = true
  try { const res = await configApi.testAlert(buildPayload()); showResult(res.data) }
  catch(e) { ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message)) }
  finally { testing.value = false }
}
const testRow = async (row) => {
  testingId.value = row.id
  try { const res = await configApi.testAlertById(row.id); showResult(res.data) }
  catch(e) { ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message)) }
  finally { testingId.value = null }
}

const saveAlert = async () => {
  try {
    const payload = buildPayload()
    if (editId.value) { await configApi.updateAlert(editId.value, payload); ElMessage.success('更新成功') }
    else { await configApi.createAlert(payload); ElMessage.success('创建成功') }
    showForm.value = false; load()
  } catch(e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
}

const delAlert = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该告警渠道？', '提示', { type: 'warning' })
    await configApi.deleteAlert(row.id); ElMessage.success('已删除'); load()
  } catch(e) { /* 取消 */ }
}
const toggleAlert = async (row, val) => {
  try { await configApi.updateAlert(row.id, { enabled: val }); ElMessage.success(val?'已启用':'已禁用'); load() }
  catch(e) { ElMessage.error('操作失败'); load() }
}
</script>
