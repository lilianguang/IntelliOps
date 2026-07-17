<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px"><h2>数据源配置</h2><el-button type="primary" @click="addDS">新增</el-button></div>
    <el-table :data="list" stripe>
      <el-table-column prop="name" label="名称" width="150" />
      <el-table-column prop="ds_type" label="类型" width="100">
       <template #default="{row}">{{ {es:'Elasticsearch',mysql:'MySQL',redis:'Redis',prometheus:'Prometheus'}[row.ds_type]||row.ds_type }}</template>
      </el-table-column>
      <el-table-column label="地址" width="220">
        <template #default="{row}">{{ row.host }}:{{ row.port }}</template>
      </el-table-column>
      <el-table-column label="启用" width="80"><template #default="{row}"><el-switch :model-value="!!row.enabled" @change="(v)=>toggleDS(row,v)" /></template></el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{row}">
          <el-button text type="success" size="small" :loading="testingId===row.id" @click="testRow(row)">连通性测试</el-button>
          <el-button text type="primary" size="small" @click="editDS(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="delDS(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showForm" :title="editId?'编辑数据源':'新增数据源'" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="form.ds_type" @change="onTypeChange"><el-option label="Elasticsearch" value="es" /><el-option label="MySQL" value="mysql" /><el-option label="Redis" value="redis" /><el-option label="Prometheus" value="prometheus" /></el-select></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.host" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item v-if="form.ds_type==='es' || form.ds_type==='prometheus'" label="启用SSL"><el-switch v-model="sslEnabled" /></el-form-item>
        <el-form-item v-if="form.ds_type==='mysql'" label="数据库"><el-input v-model="dbName" placeholder="aiops" /></el-form-item>
        <el-form-item v-if="form.ds_type==='redis'" label="DB"><el-input-number v-model="redisDb" :min="0" :max="15" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button :loading="testing" @click="testForm">连通性测试</el-button>
        <el-button type="primary" @click="saveDS">保存</el-button>
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
const sslEnabled = ref(false); const dbName = ref('aiops'); const redisDb = ref(0)
const form = ref(defaultForm())

function defaultForm() { return { name:'', ds_type:'es', host:'', port:9200, username:'', password:'' } }

function onTypeChange() {
  const portMap = { es: 9200, mysql: 3306, redis: 6379, prometheus: 9090 }
  form.value.port = portMap[form.value.ds_type] || 9090
}

function buildExtra() {
  const extra = {}
  if (form.value.ds_type === 'es') extra.use_ssl = sslEnabled.value
  if (form.value.ds_type === 'mysql') extra.database = dbName.value
  if (form.value.ds_type === 'redis') extra.db = redisDb.value
  if (form.value.ds_type === 'prometheus') extra.use_ssl = sslEnabled.value
  return extra
}

function syncExtra(ds) {
  const e = ds.extra_config || {}
  sslEnabled.value = !!e.use_ssl
  dbName.value = e.database || 'aiops'
  redisDb.value = e.db || 0
}

const load = async () => { try { const r = await configApi.listDS(); list.value = r.data } catch(e) { console.error(e) } }
onMounted(load)

const addDS = () => { editId.value = null; form.value = defaultForm(); sslEnabled.value=false; dbName.value='aiops'; redisDb.value=0; showForm.value = true }
const editDS = (row) => {
  editId.value = row.id
  form.value = { name:row.name, ds_type:row.ds_type, host:row.host, port:row.port, username:row.username||'', password:row.password||'' }
  syncExtra(row); showForm.value = true
}

const testForm = async () => {
  testing.value = true
  try {
    const payload = { ...form.value, extra_config: buildExtra() }
    const res = await configApi.testDS(payload)
    showResult(res.data)
  } catch(e) { ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message)) }
  finally { testing.value = false }
}

const testRow = async (row) => {
  testingId.value = row.id
  try {
    const res = await configApi.testDSById(row.id)
    showResult(res.data)
  } catch(e) { ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message)) }
  finally { testingId.value = null }
}

const showResult = (d) => {
  d.success
    ? ElMessage.success(`${d.message} (${d.latency_ms}ms)`)
    : ElMessage.error(d.message || '连接失败')
}

const saveDS = async () => {
  try {
    const payload = { ...form.value, extra_config: buildExtra() }
    if (editId.value) { await configApi.updateDS(editId.value, payload); ElMessage.success('更新成功') }
    else { await configApi.createDS(payload); ElMessage.success('创建成功') }
    showForm.value = false; load()
  } catch(e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
}

const delDS = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该数据源？', '提示', { type: 'warning' })
    await configApi.deleteDS(row.id); ElMessage.success('已删除'); load()
  } catch(e) { /* 取消 */ }
}

const toggleDS = async (row, val) => {
  try { await configApi.updateDS(row.id, { enabled: val }); ElMessage.success(val?'已启用':'已禁用'); load() }
  catch(e) { ElMessage.error('操作失败'); load() }
}
</script>
