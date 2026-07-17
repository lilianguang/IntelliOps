<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px"><h2>大模型配置</h2><el-button type="primary" @click="addLLM">新增</el-button></div>
    <el-table :data="list" stripe>
      <el-table-column prop="name" label="名称" width="150" />
      <el-table-column prop="model_name" label="模型" width="120" />
      <el-table-column prop="api_base" label="API地址" min-width="250" />
      <el-table-column prop="temperature" label="温度" width="80" />
      <el-table-column label="优先级" width="90">
        <template #default="{row}"><el-tag size="small" :type="row.priority===0?'success':'info'">{{ row.priority===0?'主':'备' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="启用" width="80"><template #default="{row}"><el-switch :model-value="!!row.enabled" @change="(v)=>toggleLLM(row,v)" /></template></el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{row}">
          <el-button text type="success" size="small" :loading="testingId===row.id" @click="testRow(row)">连通性测试</el-button>
          <el-button text type="primary" size="small" @click="editLLM(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="delLLM(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="showForm" :title="editId?'编辑大模型':'新增大模型'" width="600px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="模型名称"><el-input v-model="form.model_name" placeholder="qwen3" /></el-form-item>
        <el-form-item label="API地址"><el-input v-model="form.api_base" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password /></el-form-item>
        <el-form-item label="温度"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="0" /><span style="margin-left:8px;color:#909399;font-size:12px">0=主模型</span></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button :loading="testing" @click="testForm">连通性测试</el-button>
        <el-button type="primary" @click="saveLLM">保存</el-button>
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
const form = ref(defaultForm())

function defaultForm() { return { name:'', model_name:'qwen3', api_base:'', api_key:'', temperature:0.7, priority:0 } }

const showResult = (d) => d.success ? ElMessage.success(`${d.message} (${d.latency_ms}ms)`) : ElMessage.error(d.message || '连接失败')

const load = async () => { try { const r = await configApi.listLLMs(); list.value = r.data } catch(e) { console.error(e) } }
onMounted(load)

const addLLM = () => { editId.value = null; form.value = defaultForm(); showForm.value = true }
const editLLM = (row) => { editId.value = row.id; form.value = { name:row.name, model_name:row.model_name, api_base:row.api_base, api_key:row.api_key, temperature:row.temperature, priority:row.priority }; showForm.value = true }

const testForm = async () => {
  testing.value = true
  try { const res = await configApi.testLLM(form.value); showResult(res.data) }
  catch(e) { ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message)) }
  finally { testing.value = false }
}
const testRow = async (row) => {
  testingId.value = row.id
  try { const res = await configApi.testLLMById(row.id); showResult(res.data) }
  catch(e) { ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message)) }
  finally { testingId.value = null }
}

const saveLLM = async () => {
  try {
    if (editId.value) { await configApi.updateLLM(editId.value, form.value); ElMessage.success('更新成功') }
    else { await configApi.createLLM(form.value); ElMessage.success('创建成功') }
    showForm.value = false; load()
  } catch(e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
}

const delLLM = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该大模型配置？', '提示', { type: 'warning' })
    await configApi.deleteLLM(row.id); ElMessage.success('已删除'); load()
  } catch(e) { /* 取消 */ }
}
const toggleLLM = async (row, val) => {
  try { await configApi.updateLLM(row.id, { enabled: val }); ElMessage.success(val?'已启用':'已禁用'); load() }
  catch(e) { ElMessage.error('操作失败'); load() }
}
</script>
