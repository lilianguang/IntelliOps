<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2 style="margin:0">负载均衡</h2>
      <div>
        <el-button :icon="Refresh" @click="syncData" :loading="syncing">同步LB</el-button>
        <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls">
          <el-button :icon="Upload">导入</el-button>
        </el-upload>
        <el-button :icon="Download" @click="handleExport">导出</el-button>
        <el-button :icon="Setting" @click="showColSetting=true">列设置</el-button>
      </div>
    </div>

    <!-- 搜索栏 -->
    <el-card shadow="never" style="margin-bottom:15px">
      <el-form :inline="true" @submit.prevent="load">
        <el-form-item>
          <el-input v-model="keyword" placeholder="搜索VIP/后端IP/业务..." clearable style="width:280px" :prefix-icon="Search" @keyup.enter="load" />
        </el-form-item>
        <el-form-item label="匹配方式">
          <el-radio-group v-model="searchType" @change="load">
            <el-radio-button value="fuzzy">模糊</el-radio-button>
            <el-radio-button value="exact">精确</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="sourceFilter" clearable placeholder="全部" style="width:120px" @change="load">
            <el-option label="自动解析" value="auto" />
            <el-option label="手动录入" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
          <el-button type="success" :icon="Plus" @click="openForm()">新增</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card shadow="never">
      <el-table :data="list" stripe v-loading="loading" border style="width:100%" empty-text="暂无数据">
        <el-table-column type="index" label="序号" width="60" align="center" header-align="center" />
        <el-table-column v-for="col in visibleColumns" :key="col.field_name" :prop="col.field_name" :label="col.label"
          :width="col.width || undefined" align="center" header-align="center" show-overflow-tooltip>
          <template #default="{row}">
            <template v-if="col.column_type === 'tag'">
              <el-tag :type="tagType(row[col.field_name])" size="small">{{ row[col.field_name] || '-' }}</el-tag>
            </template>
            <template v-else>{{ row[col.field_name] !== null && row[col.field_name] !== undefined ? row[col.field_name] : '-' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="80" align="center" header-align="center">
          <template #default="{row}">
            <el-tag :type="row.source === 'auto' ? 'info' : 'success'" size="small">{{ row.source === 'auto' ? '自动' : '手动' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center" header-align="center">
          <template #default="{row}">
            <el-button text type="primary" size="small" @click="openForm(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="delRecord(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="display:flex;justify-content:flex-end;margin-top:15px">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
          :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
          @size-change="load" @current-change="load" />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showForm" :title="editId ? '编辑负载均衡' : '新增负载均衡'" width="680px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="VIP"><el-input v-model="form.vip" placeholder="如 192.67.1.8" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="VIP端口"><el-input-number v-model="form.vip_port" :min="1" :max="65535" controls-position="right" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="协议"><el-select v-model="form.protocol" clearable style="width:100%"><el-option label="tcp" value="tcp" /><el-option label="udp" value="udp" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="VPN实例"><el-input v-model="form.vpn_instance" placeholder="VPN实例" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="后端IP"><el-input v-model="form.backend_ip" type="textarea" :rows="2" placeholder="多个用逗号分隔" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="后端端口"><el-input v-model="form.backend_port" type="textarea" :rows="2" placeholder="多个用逗号分隔" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="业务"><el-input v-model="form.business" placeholder="业务名称" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="备注"><el-input v-model="form.remarks" placeholder="备注" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRecord">保存</el-button>
      </template>
    </el-dialog>

    <!-- 列设置弹窗 -->
    <el-dialog v-model="showColSetting" title="列设置" width="560px" destroy-on-close>
      <el-alert type="info" :closable="false" style="margin-bottom:15px">
        <template #title>勾选需要显示的列，修改列宽。点击"新增自定义列"可添加自定义字段</template>
      </el-alert>
      <el-table :data="colSettingList" border size="small" row-key="field_name" max-height="400">
        <el-table-column label="显示" width="60" align="center">
          <template #default="{row}"><el-checkbox v-model="row.visible" /></template>
        </el-table-column>
        <el-table-column label="字段名" prop="label" width="120" align="center" />
        <el-table-column label="标识" prop="field_name" width="150" align="center">
          <template #default="{row}"><el-tag size="small" type="info">{{ row.field_name }}</el-tag></template>
        </el-table-column>
        <el-table-column label="列宽(px)" width="120" align="center">
          <template #default="{row}"><el-input-number v-model="row.width" :min="60" :max="400" :step="10" size="small" controls-position="right" style="width:100px" /></template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{row}"><el-button v-if="row.is_custom" text type="danger" size="small" @click="deleteColMeta(row)">删除</el-button></template>
        </el-table-column>
      </el-table>
      <div style="margin-top:10px"><el-button text type="primary" :icon="Plus" @click="showAddCol=true">新增自定义列</el-button></div>
      <template #footer>
        <el-button @click="showColSetting=false">取消</el-button>
        <el-button type="primary" @click="saveColSetting">保存设置</el-button>
      </template>
    </el-dialog>

    <!-- 新增自定义列弹窗 -->
    <el-dialog v-model="showAddCol" title="新增自定义列" width="420px" append-to-body destroy-on-close>
      <el-form :model="newCol" label-width="80px">
        <el-form-item label="字段名"><el-input v-model="newCol.field_name" placeholder="英文标识，如 remark2" /></el-form-item>
        <el-form-item label="显示名"><el-input v-model="newCol.label" placeholder="中文名称" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="newCol.column_type" style="width:100%">
            <el-option label="文本" value="text" /><el-option label="数字" value="number" />
            <el-option label="标签" value="tag" /><el-option label="IP" value="ip" />
          </el-select>
        </el-form-item>
        <el-form-item label="列宽"><el-input-number v-model="newCol.width" :min="60" :max="400" :step="10" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddCol=false">取消</el-button>
        <el-button type="primary" @click="addCustomCol">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { logicalApi } from '../../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Setting, Refresh, Upload, Download } from '@element-plus/icons-vue'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const keyword = ref('')
const searchType = ref('fuzzy')
const sourceFilter = ref('')

const columns = ref([])
const visibleColumns = computed(() => columns.value.filter(c => c.visible && c.field_name !== 'id' && c.field_name !== 'source' && c.field_name !== 'source_key' && c.field_name !== 'device_ip' && c.field_name !== 'created_at' && c.field_name !== 'updated_at'))

const loadMeta = async () => {
  try {
    const res = await logicalApi.getMeta('lb_mapping')
    columns.value = res.data.columns || []
  } catch { columns.value = [] }
}

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value, search_type: searchType.value }
    if (keyword.value) params.keyword = keyword.value
    if (sourceFilter.value) params.source = sourceFilter.value
    const res = await logicalApi.lbMappingList(params)
    list.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

const resetFilters = () => { keyword.value = ''; searchType.value = 'fuzzy'; sourceFilter.value = ''; page.value = 1; load() }

// 同步
const syncing = ref(false)
const syncData = async () => {
  syncing.value = true
  try {
    const res = await logicalApi.lbMappingSync()
    ElMessage.success(`同步完成，共 ${res.data.total} 条`)
    load()
  } catch (e) {
    ElMessage.error('同步失败: ' + (e.response?.data?.detail || e.message))
  } finally { syncing.value = false }
}

// 导出
const handleExport = async () => {
  try {
    const res = await logicalApi.lbMappingExport()
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url; a.download = '负载均衡.xlsx'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) { ElMessage.error('导出失败') }
}

// 导入
const handleImport = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await logicalApi.lbMappingImport(formData)
    ElMessage.success(`导入完成: 新增${res.data.created} 更新${res.data.updated} 失败${res.data.failed}`)
    load()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  }
  return false
}

// CRUD
const showForm = ref(false)
const editId = ref(null)
const saving = ref(false)
const defaultForm = () => ({ vip: '', vip_port: null, protocol: '', vpn_instance: '', backend_ip: '', backend_port: '', business: '', remarks: '' })
const form = ref(defaultForm())

const openForm = (row) => {
  if (row) {
    editId.value = row.id
    form.value = { ...defaultForm(), ...row }
  } else {
    editId.value = null
    form.value = defaultForm()
  }
  showForm.value = true
}

const saveRecord = async () => {
  saving.value = true
  try {
    const data = {}
    for (const [k, v] of Object.entries(form.value)) {
      if (v !== '' && v !== null && v !== undefined) data[k] = v
    }
    if (editId.value) {
      await logicalApi.lbMappingUpdate(editId.value, data)
      ElMessage.success('更新成功')
    } else {
      await logicalApi.lbMappingCreate(data)
      ElMessage.success('创建成功')
    }
    showForm.value = false
    load()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally { saving.value = false }
}

const delRecord = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该记录？', '提示', { type: 'warning' })
    await logicalApi.lbMappingDel(row.id)
    ElMessage.success('已删除')
    load()
  } catch { /* 取消 */ }
}

// 列设置
const showColSetting = ref(false)
const colSettingList = ref([])
const showAddCol = ref(false)
const newCol = ref({ field_name: '', label: '', column_type: 'text', width: 120 })

const tagType = (v) => {
  if (!v) return 'info'
  const s = String(v).toLowerCase()
  if (['tcp', 'enable', 'online', 'up'].includes(s)) return 'success'
  if (['udp', 'disable', 'down'].includes(s)) return 'warning'
  return 'info'
}

const saveColSetting = async () => {
  try {
    for (let i = 0; i < colSettingList.value.length; i++) {
      const c = colSettingList.value[i]
      await logicalApi.updateColumn('lb_mapping', c.id, { visible: c.visible, width: c.width, sort_order: i })
    }
    await loadMeta()
    showColSetting.value = false
    ElMessage.success('列设置已保存')
  } catch (e) { ElMessage.error('保存失败') }
}

const addCustomCol = async () => {
  if (!newCol.value.field_name || !newCol.value.label) {
    ElMessage.warning('请填写字段名和显示名'); return
  }
  try {
    await logicalApi.createColumn('lb_mapping', { ...newCol.value })
    ElMessage.success('已添加自定义列')
    showAddCol.value = false
    newCol.value = { field_name: '', label: '', column_type: 'text', width: 120 }
    await loadMeta()
    colSettingList.value = columns.value.map(c => ({ ...c }))
  } catch (e) { ElMessage.error('添加失败: ' + (e.response?.data?.detail || e.message)) }
}

const deleteColMeta = async (col) => {
  try {
    await ElMessageBox.confirm(`确认删除自定义列「${col.label}」？`, '提示', { type: 'warning' })
    await logicalApi.deleteColumn('lb_mapping', col.id)
    colSettingList.value = colSettingList.value.filter(c => c.id !== col.id)
    await loadMeta()
    ElMessage.success('已删除')
  } catch { /* 取消 */ }
}

watch(showColSetting, (val) => { if (val) colSettingList.value = columns.value.map(c => ({ ...c })) })

onMounted(async () => {
  await loadMeta()
  load()
})
</script>
