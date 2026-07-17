<template>
  <div>
    <!-- 页面标题 + 操作栏 -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2 style="margin:0">IT资源管理</h2>
      <div>
        <el-button :icon="Setting" @click="showColSetting=true">列设置</el-button>
        <el-button type="success" :icon="Upload" @click="showImport=true">Excel导入</el-button>
        <el-button type="primary" :icon="Plus" @click="openForm()">新增资产</el-button>
      </div>
    </div>

    <!-- 搜索筛选栏 -->
    <el-card shadow="never" style="margin-bottom:15px">
      <el-form :inline="true" @submit.prevent="load">
        <el-form-item>
          <el-input v-model="filters.keyword" placeholder="搜索编号/名称/IP/负责人/序列号" clearable style="width:280px" :prefix-icon="Search" @keyup.enter="load" />
        </el-form-item>
        <el-form-item>
          <el-select v-model="filters.asset_type" placeholder="资产类型" clearable style="width:140px">
            <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width:120px">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select v-model="filters.environment" placeholder="环境" clearable style="width:120px">
            <el-option v-for="e in envOptions" :key="e.value" :label="e.label" :value="e.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 资产表格 -->
    <el-card shadow="never">
      <el-table :data="list" stripe v-loading="loading" border style="width:100%">
        <el-table-column
          v-for="col in visibleColumns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width || undefined"
          :min-width="col.minWidth || undefined"
          align="center"
          header-align="center"
          show-overflow-tooltip
        >
          <template #default="{row}">
            <template v-if="col.prop === 'asset_type'">{{ typeLabel(row.asset_type) }}</template>
            <template v-else-if="col.prop === 'status'">
              <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
            <template v-else-if="col.prop === 'environment'">{{ envLabel(row.environment) }}</template>
            <template v-else>{{ row[col.prop] || '-' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center" header-align="center">
          <template #default="{row}">
            <el-button text type="primary" size="small" @click="openForm(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="delAsset(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="display:flex;justify-content:flex-end;margin-top:15px">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="load"
          @current-change="load"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showForm" :title="editId ? '编辑资产' : '新增资产'" width="680px" destroy-on-close>
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-row :gutter="16" v-for="pair in formFieldPairs" :key="pair[0]?.prop">
          <el-col :span="12" v-for="field in pair" :key="field.prop">
            <el-form-item :label="field.label" :prop="field.prop === 'asset_code' ? 'asset_code' : field.prop === 'name' ? 'name' : undefined">
              <el-select v-if="field.options" v-model="form[field.prop]" :clearable="field.clearable !== false" style="width:100%" :placeholder="field.placeholder">
                <el-option v-for="o in field.options" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-input v-else v-model="form[field.prop]" :disabled="field.prop === 'asset_code' && !!editId" :placeholder="field.placeholder" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remarks" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAsset">保存</el-button>
      </template>
    </el-dialog>

    <!-- Excel导入弹窗 -->
    <el-dialog v-model="showImport" title="Excel导入资产" width="520px" destroy-on-close>
      <el-alert type="info" :closable="false" style="margin-bottom:15px">
        <template #title>Excel表头要求</template>
        表头必须包含：<strong>编号</strong>、<strong>名称</strong>（必填）。<br/>
        可选列：类型、型号、序列号、IP地址、状态、环境、区域、机房信息、机柜信息、组织归属、负责人、维保信息、备注<br/>
        状态支持：在线/离线/维护中/已报废
      </el-alert>
      <el-upload
        ref="uploadRef"
        drag
        action=""
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.xls"
        :on-change="onFileChange"
        :on-exceed="() => ElMessage.warning('只能上传一个文件')"
      >
        <el-icon style="font-size:40px;color:#909399"><Upload /></el-icon>
        <div style="margin-top:8px">将Excel文件拖到此处，或<em>点击上传</em></div>
      </el-upload>
      <template #footer>
        <el-button @click="showImport=false">取消</el-button>
        <el-button type="primary" :loading="importing" :disabled="!importFile" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 列设置弹窗 -->
    <el-dialog v-model="showColSetting" title="表格列设置" width="560px" destroy-on-close>
      <el-alert type="info" :closable="false" style="margin-bottom:15px">
        <template #title>使用说明</template>
        勾选需要显示的列，拖动排序可调整列的显示顺序，修改宽度可自定义列宽。设置完成后点击"保存设置"。
      </el-alert>
      <el-table :data="colSettingList" border size="small" row-key="prop" max-height="450">
        <el-table-column label="排序" width="60" align="center">
          <template #default>
            <el-icon style="cursor:move;color:#909399" class="drag-handle"><Rank /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="显示" width="60" align="center">
          <template #default="{row}">
            <el-checkbox v-model="row.visible" />
          </template>
        </el-table-column>
        <el-table-column label="字段名" prop="label" width="100" align="center" />
        <el-table-column label="字段标识" prop="prop" width="140" align="center">
          <template #default="{row}"><el-tag size="small" type="info">{{ row.prop }}</el-tag></template>
        </el-table-column>
        <el-table-column label="列宽(px)" width="120" align="center">
          <template #default="{row}">
            <el-input-number v-model="row.width" :min="60" :max="400" :step="10" size="small" controls-position="right" style="width:100px" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="resetColSetting">恢复默认</el-button>
        <el-button @click="showColSetting=false">取消</el-button>
        <el-button type="primary" @click="saveColSetting">保存设置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { cmdbApi } from '../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Search, Setting, Rank } from '@element-plus/icons-vue'

// ========== 选项数据 ==========
const typeOptions = [
  { value: 'server', label: '服务器' },
  { value: 'network', label: '网络设备' },
  { value: 'storage', label: '存储设备' },
  { value: 'security', label: '安全设备' },
  { value: 'software', label: '软件系统' },
  { value: 'other', label: '其他' },
]
const statusOptions = [
  { value: 'online', label: '在线' },
  { value: 'offline', label: '离线' },
  { value: 'maintenance', label: '维护中' },
  { value: 'decommissioned', label: '已报废' },
]
const envOptions = [
  { value: 'production', label: '生产' },
  { value: 'test', label: '测试' },
  { value: 'development', label: '开发' },
  { value: 'dr', label: '灾备' },
]

const typeLabel = (v) => (typeOptions.find((t) => t.value === v)?.label) || v || '-'
const statusLabel = (v) => (statusOptions.find((s) => s.value === v)?.label) || v || '-'
const envLabel = (v) => (envOptions.find((e) => e.value === v)?.label) || v || '-'
const statusTag = (v) => ({ online: 'success', offline: 'info', maintenance: 'warning', decommissioned: 'danger' }[v] || 'info')

// ========== 列配置 ==========
const STORAGE_KEY = 'cmdb_column_config_v1'

const DEFAULT_COLUMNS = [
  { prop: 'asset_code',    label: '编号',     width: 120, visible: true },
  { prop: 'name',          label: '名称',     width: 160, visible: true },
  { prop: 'asset_type',    label: '类型',     width: 100, visible: true },
  { prop: 'model',         label: '型号',     width: 120, visible: true },
  { prop: 'serial_number', label: '序列号',   width: 130, visible: true },
  { prop: 'ip_address',    label: 'IP地址',   width: 140, visible: true },
  { prop: 'status',        label: '状态',     width: 90,  visible: true },
  { prop: 'environment',   label: '环境',     width: 80,  visible: true },
  { prop: 'region',        label: '区域',     width: 100, visible: true },
  { prop: 'datacenter',    label: '机房',     width: 120, visible: true },
  { prop: 'rack_info',     label: '机柜',     width: 100, visible: true },
  { prop: 'organization',  label: '组织归属', width: 120, visible: true },
  { prop: 'owner',         label: '负责人',   width: 90,  visible: true },
  { prop: 'warranty_info', label: '维保信息', width: 150, visible: true },
  { prop: 'remarks',       label: '备注',     width: 120, visible: true },
]

function loadColConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw)
      const savedMap = new Map(saved.map(c => [c.prop, c]))
      return DEFAULT_COLUMNS.map(dc => {
        const s = savedMap.get(dc.prop)
        return s ? { ...dc, visible: s.visible !== false, width: s.width || dc.width } : { ...dc }
      })
    }
  } catch { /* ignore */ }
  return DEFAULT_COLUMNS.map(c => ({ ...c }))
}

const columnConfig = ref(loadColConfig())
const visibleColumns = computed(() => columnConfig.value.filter(c => c.visible))

// 列设置弹窗
const showColSetting = ref(false)
const colSettingList = ref([])

const openColSetting = () => {
  colSettingList.value = columnConfig.value.map(c => ({ ...c }))
}
watch(showColSetting, (val) => { if (val) openColSetting() })

const saveColSetting = () => {
  columnConfig.value = colSettingList.value.map(c => ({ ...c }))
  localStorage.setItem(STORAGE_KEY, JSON.stringify(columnConfig.value))
  showColSetting.value = false
  ElMessage.success('列设置已保存')
}

const resetColSetting = () => {
  colSettingList.value = DEFAULT_COLUMNS.map(c => ({ ...c }))
  ElMessage.success('已恢复默认设置，点击"保存设置"生效')
}

// ========== 表单字段配置 ==========
const formFields = [
  { prop: 'asset_code',  label: '编号',     placeholder: '唯一编号' },
  { prop: 'name',        label: '名称',     placeholder: '资产名称' },
  { prop: 'asset_type',  label: '类型',     placeholder: '资产类型', options: typeOptions },
  { prop: 'model',       label: '型号',     placeholder: '设备型号' },
  { prop: 'serial_number', label: '序列号', placeholder: '序列号' },
  { prop: 'ip_address',  label: 'IP地址',   placeholder: '如 192.168.1.1' },
  { prop: 'status',      label: '状态',     placeholder: '状态', options: statusOptions, clearable: false },
  { prop: 'environment', label: '环境',     placeholder: '环境', options: envOptions },
  { prop: 'region',      label: '区域',     placeholder: '如: 华东' },
  { prop: 'datacenter',  label: '机房信息', placeholder: '机房名称/地址' },
  { prop: 'rack_info',   label: '机柜信息', placeholder: '如: A区-3排-12柜' },
  { prop: 'organization', label: '组织归属', placeholder: '部门/组织' },
  { prop: 'owner',       label: '负责人',   placeholder: '负责人姓名' },
  { prop: 'warranty_info', label: '维保信息', placeholder: '维保厂商/到期日' },
]

const formFieldPairs = computed(() => {
  const pairs = []
  for (let i = 0; i < formFields.length; i += 2) {
    pairs.push(formFields.slice(i, i + 2))
  }
  return pairs
})

// ========== 列表 ==========
const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ keyword: '', asset_type: '', status: '', environment: '' })

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filters.value.keyword) params.keyword = filters.value.keyword
    if (filters.value.asset_type) params.asset_type = filters.value.asset_type
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.environment) params.environment = filters.value.environment
    const res = await cmdbApi.list(params)
    list.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}
onMounted(load)

const resetFilters = () => {
  filters.value = { keyword: '', asset_type: '', status: '', environment: '' }
  page.value = 1
  load()
}

// ========== 新增/编辑 ==========
const showForm = ref(false)
const editId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const rules = {
  asset_code: [{ required: true, message: '请输入资产编号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

function defaultForm() {
  return {
    asset_code: '', name: '', asset_type: '', model: '', serial_number: '',
    ip_address: '', status: 'online', environment: '', region: '', datacenter: '',
    rack_info: '', organization: '', owner: '', warranty_info: '', remarks: '',
  }
}

const form = ref(defaultForm())

const openForm = (row) => {
  if (row) {
    editId.value = row.id
    form.value = {
      asset_code: row.asset_code, name: row.name, asset_type: row.asset_type || '',
      model: row.model || '', serial_number: row.serial_number || '', ip_address: row.ip_address || '',
      status: row.status || 'online', environment: row.environment || '', region: row.region || '',
      datacenter: row.datacenter || '', rack_info: row.rack_info || '', organization: row.organization || '',
      owner: row.owner || '', warranty_info: row.warranty_info || '', remarks: row.remarks || '',
    }
  } else {
    editId.value = null
    form.value = defaultForm()
  }
  showForm.value = true
}

const saveAsset = async () => {
  await formRef.value?.validate()
  saving.value = true
  try {
    const payload = {}
    for (const [k, v] of Object.entries(form.value)) {
      if (v !== '' && v !== null && v !== undefined) payload[k] = v
    }
    if (!payload.asset_code || !payload.name) {
      ElMessage.warning('编号和名称不能为空'); saving.value = false; return
    }
    if (editId.value) {
      await cmdbApi.update(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await cmdbApi.create(payload)
      ElMessage.success('创建成功')
    }
    showForm.value = false
    load()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

// ========== 删除 ==========
const delAsset = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除资产「${row.name}」(编号: ${row.asset_code})？`, '提示', { type: 'warning' })
    await cmdbApi.del(row.id)
    ElMessage.success('已删除')
    load()
  } catch { /* 取消 */ }
}

// ========== Excel导入 ==========
const showImport = ref(false)
const importFile = ref(null)
const importing = ref(false)
const uploadRef = ref(null)

const onFileChange = (file) => {
  importFile.value = file.raw
}

const doImport = async () => {
  if (!importFile.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const res = await cmdbApi.importExcel(fd)
    const d = res.data
    if (d.failed > 0 || d.errors?.length) {
      ElMessage.warning(`导入完成：新增${d.created}条，更新${d.updated}条，失败${d.failed}条`)
      if (d.errors?.length) console.warn('导入错误:', d.errors)
    } else {
      ElMessage.success(`导入成功：新增${d.created}条，更新${d.updated}条`)
    }
    showImport.value = false
    importFile.value = null
    uploadRef.value?.clearFiles()
    load()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    importing.value = false
  }
}
</script>
