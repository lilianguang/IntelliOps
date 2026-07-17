<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2 style="margin:0">{{ tableLabel }}</h2>
      <div>
        <el-upload :show-file-list="false" :before-upload="handleImport" accept=".xlsx,.xls" style="display:inline-block;margin-right:8px">
          <el-button :icon="Upload">导入</el-button>
        </el-upload>
        <el-button :icon="Download" @click="handleExport">导出</el-button>
        <el-button :icon="Setting" @click="showColSetting=true">列设置</el-button>
        <el-button type="primary" :icon="Plus" @click="openForm()">新增</el-button>
      </div>
    </div>

    <!-- 搜索栏 -->
    <el-card shadow="never" style="margin-bottom:15px">
      <el-form :inline="true" @submit.prevent="load">
        <el-form-item>
          <el-input v-model="keyword" placeholder="搜索IP/名称/关键字..." clearable style="width:280px" :prefix-icon="Search" @keyup.enter="load" />
        </el-form-item>
        <el-form-item label="匹配方式">
          <el-radio-group v-model="searchType" @change="load">
            <el-radio-button value="fuzzy">模糊</el-radio-button>
            <el-radio-button value="exact">精确</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-input v-model="deviceIp" placeholder="设备IP" clearable style="width:160px" @keyup.enter="load" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
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
            <template v-else>{{ getFieldValue(row, col.field_name) }}</template>
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
    <el-dialog v-model="showForm" :title="editId ? '编辑记录' : '新增记录'" width="680px" destroy-on-close>
      <el-form :model="form" label-width="120px">
        <el-row :gutter="16" v-for="pair in formFieldPairs" :key="pair[0]?.field_name">
          <el-col :span="12" v-for="field in pair" :key="field.field_name">
            <el-form-item :label="field.label">
              <el-select v-if="field.column_type === 'tag'" v-model="form[field.field_name]" clearable placeholder="选择" style="width:100%">
                <el-option v-for="opt in getSelectOptions(field)" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <el-input-number v-else-if="field.column_type === 'number'" v-model="form[field.field_name]" controls-position="right" style="width:100%" />
              <el-input v-else v-model="form[field.field_name]" :placeholder="field.label" />
            </el-form-item>
          </el-col>
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
        <template #title>勾选需要显示的列，拖动排序，修改列宽</template>
      </el-alert>
      <el-table :data="colSettingList" border size="small" row-key="field_name" max-height="500">
        <el-table-column label="显示" width="60" align="center">
          <template #default="{row}"><el-checkbox v-model="row.visible" /></template>
        </el-table-column>
        <el-table-column label="字段名" prop="label" width="120" align="center" />
        <el-table-column label="标识" prop="field_name" width="150" align="center">
          <template #default="{row}"><el-tag size="small" type="info">{{ row.field_name }}</el-tag></template>
        </el-table-column>
        <el-table-column label="列宽(px)" width="120" align="center">
          <template #default="{row}">
            <el-input-number v-model="row.width" :min="60" :max="400" :step="10" size="small" controls-position="right" style="width:100px" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{row}">
            <el-button v-if="row.is_custom" text type="danger" size="small" @click="deleteColMeta(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="showColSetting=false">取消</el-button>
        <el-button type="primary" @click="saveColSetting">保存设置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { logicalApi } from '../../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Setting, Upload, Download } from '@element-plus/icons-vue'

const route = useRoute()

// 表名映射
const TABLE_LABELS = {
  interfaces: '接口信息', ips: 'IP地址',
}

const table = computed(() => route.params.table || '')
const tableLabel = computed(() => TABLE_LABELS[table.value] || table.value)

// ========== 列元数据 ==========
const columns = ref([])
const visibleColumns = computed(() => columns.value.filter(c => c.visible))

const loadMeta = async () => {
  try {
    const res = await logicalApi.getMeta(table.value)
    columns.value = res.data.columns || []
  } catch { columns.value = [] }
}

// ========== 列表 ==========
const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const keyword = ref('')
const searchType = ref('fuzzy')
const deviceIp = ref('')

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value, search_type: searchType.value }
    if (keyword.value) params.keyword = keyword.value
    if (deviceIp.value) params.device_ip = deviceIp.value
    const res = await logicalApi.list(table.value, params)
    list.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

const resetFilters = () => { keyword.value = ''; searchType.value = 'fuzzy'; deviceIp.value = ''; page.value = 1; load() }

// ========== 导出/导入 ==========
const handleExport = async () => {
  try {
    const res = await logicalApi.exportTable(table.value)
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url; a.download = `${tableLabel.value}.xlsx`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) { ElMessage.error('导出失败') }
}

const handleImport = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await logicalApi.importTable(table.value, formData)
    ElMessage.success(`导入完成: 新增${res.data.created} 更新${res.data.updated} 失败${res.data.failed}`)
    load()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  }
  return false
}

// ========== 新增/编辑 ==========
const showForm = ref(false)
const editId = ref(null)
const saving = ref(false)
const form = ref({})

const editableColumns = computed(() => columns.value.filter(c => c.field_name !== 'id' && c.field_name !== 'created_at' && c.field_name !== 'updated_at'))
const formFieldPairs = computed(() => {
  const pairs = []
  for (let i = 0; i < editableColumns.value.length; i += 2) pairs.push(editableColumns.value.slice(i, i + 2))
  return pairs
})

const getSelectOptions = (field) => {
  try { return field.select_options ? JSON.parse(field.select_options) : [] } catch { return [] }
}

const getFieldValue = (row, fieldName) => {
  const val = row[fieldName]
  if (val === null || val === undefined) return row._custom_fields?.[fieldName] || '-'
  return val
}

const tagType = (v) => {
  if (!v) return 'info'
  const s = String(v).toLowerCase()
  if (['permit', 'enable', 'online', 'up', 'true', '1'].includes(s)) return 'success'
  if (['deny', 'disable', 'offline', 'down', 'shutdown', 'false', '0'].includes(s)) return 'danger'
  return 'info'
}

const openForm = (row) => {
  if (row) {
    editId.value = row.id
    const f = {}
    for (const col of editableColumns.value) {
      f[col.field_name] = row[col.field_name] ?? row._custom_fields?.[col.field_name] ?? ''
    }
    form.value = f
  } else {
    editId.value = null
    const f = {}
    for (const col of editableColumns.value) f[col.field_name] = ''
    form.value = f
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
      await logicalApi.update(table.value, editId.value, data)
      ElMessage.success('更新成功')
    } else {
      await logicalApi.create(table.value, data)
      ElMessage.success('创建成功')
    }
    showForm.value = false
    load()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally { saving.value = false }
}

// ========== 删除 ==========
const delRecord = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该记录？', '提示', { type: 'warning' })
    await logicalApi.del(table.value, row.id)
    ElMessage.success('已删除')
    load()
  } catch { /* 取消 */ }
}

// ========== 列设置 ==========
const showColSetting = ref(false)
const colSettingList = ref([])

watch(showColSetting, (val) => {
  if (val) colSettingList.value = columns.value.map(c => ({ ...c }))
})

const saveColSetting = async () => {
  try {
    for (let i = 0; i < colSettingList.value.length; i++) {
      const c = colSettingList.value[i]
      await logicalApi.updateColumn(table.value, c.id, {
        visible: c.visible, width: c.width, sort_order: i,
      })
    }
    await loadMeta()
    showColSetting.value = false
    ElMessage.success('列设置已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

const deleteColMeta = async (col) => {
  try {
    await ElMessageBox.confirm(`确认删除自定义列「${col.label}」？`, '提示', { type: 'warning' })
    await logicalApi.deleteColumn(table.value, col.id)
    colSettingList.value = colSettingList.value.filter(c => c.id !== col.id)
    await loadMeta()
    load()
    ElMessage.success('已删除')
  } catch { /* 取消 */ }
}

// ========== 监听表名切换 ==========
watch(() => route.params.table, () => {
  page.value = 1; keyword.value = ''; searchType.value = 'fuzzy'; deviceIp.value = ''
  loadMeta().then(load)
})

onMounted(() => { loadMeta().then(load) })
</script>
