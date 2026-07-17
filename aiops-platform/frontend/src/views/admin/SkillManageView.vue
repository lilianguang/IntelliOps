<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2>技能管理</h2>
      <el-button type="primary" @click="addSkill">注册新技能</el-button>
    </div>
    <el-table :data="skills" stripe>
      <el-table-column prop="skill_name" label="技能标识" width="160" />
      <el-table-column prop="display_name" label="展示名称" width="140" />
      <el-table-column label="数据源" width="160">
        <template #default="{row}">
          <el-tag size="small" :type="row.ds_type === 'prometheus' ? 'warning' : ''">
            {{ row.datasource_name || (row.ds_type === 'es' ? 'ES(默认)' : row.ds_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="采集目标" width="200">
        <template #default="{row}">
          <span v-if="row.ds_type === 'es'">{{ row.index_pattern || '-' }}</span>
          <span v-else-if="row.ds_type === 'prometheus'">{{ getPromMetricsSummary(row) }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="scan_interval_sec" label="扫描间隔" width="100">
        <template #default="{row}">{{ row.scan_interval_sec }}s</template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{row}">
          <el-switch :model-value="!!row.enabled" @change="(v)=>toggleSkill(row.id,v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{row}">
          <el-button text type="primary" size="small" @click="editSkill(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="delSkill(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ====== 新增/编辑对话框 ====== -->
    <el-dialog v-model="showForm" :title="editId?'编辑技能':'注册新技能'" width="760px" :close-on-click-modal="false">
      <el-form :model="form" label-width="120px">
        <el-form-item label="技能标识"><el-input v-model="form.skill_name" :disabled="!!editId" /></el-form-item>
        <el-form-item label="展示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="功能描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>

        <!-- 数据源选择 -->
        <el-divider content-position="left">数据源配置</el-divider>
        <el-form-item label="关联数据源">
          <el-select v-model="form.datasource_id" style="width:100%" placeholder="选择数据源（可选）" clearable @change="onDatasourceChange">
            <el-option v-for="ds in datasources" :key="ds.id" :label="`${ds.name} (${ds.ds_type})`" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据源类型">
          <el-radio-group v-model="form.ds_type" @change="onDsTypeChange">
            <el-radio-button value="es">Elasticsearch</el-radio-button>
            <el-radio-button value="prometheus">Prometheus</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- ====== ES 配置区域 ====== -->
        <template v-if="form.ds_type === 'es'">
          <el-divider content-position="left">ES 查询配置</el-divider>
          <el-form-item label="ES索引模式"><el-input v-model="form.index_pattern" placeholder="如: h3c-net-logs-*" /></el-form-item>
          <el-form-item label="查询过滤条件" v-if="availableFields.length > 0">
            <div style="width:100%">
              <div v-for="(cond, idx) in filterConditions" :key="idx" class="cond-row">
                <el-select v-model="cond.field" placeholder="选择字段" style="width:180px" @change="onFieldChange(cond)">
                  <el-option v-for="f in availableFields" :key="f.name" :label="f.desc ? `${f.name} (${f.desc})` : f.name" :value="f.name" />
                </el-select>
                <el-select v-model="cond.operator" placeholder="操作符" style="width:140px;margin-left:8px">
                  <el-option v-for="op in getOperators(cond.field)" :key="op.value" :label="op.label" :value="op.value" />
                </el-select>
                <el-input v-model="cond.value" :placeholder="getValuePlaceholder(cond)" style="width:200px;margin-left:8px" />
                <el-button text type="danger" size="small" style="margin-left:8px" @click="removeCondition(idx)">删除</el-button>
              </div>
              <el-button text type="primary" size="small" @click="addCondition">+ 添加条件</el-button>
              <div v-if="filterConditions.length === 0" class="filter-hint">未配置查询条件时，将查询指定时间范围内的全部日志</div>
            </div>
          </el-form-item>
          <el-form-item label="查询过滤条件" v-else>
            <div class="filter-hint">该技能尚未配置字段说明，无法使用可视化过滤。请先在「字段配置」中添加字段。</div>
          </el-form-item>
        </template>

        <!-- ====== Prometheus 配置区域 ====== -->
        <template v-if="form.ds_type === 'prometheus'">
          <el-divider content-position="left">Prometheus 采集配置</el-divider>
          <el-form-item label="PromQL 查询">
            <div style="width:100%">
              <div v-for="(tmpl, idx) in promqlTemplates" :key="idx" class="cond-row">
                <el-input v-model="tmpl.name" placeholder="指标名(如:cpu_usage)" style="width:160px" />
                <el-input v-model="tmpl.promql" placeholder="PromQL表达式" style="flex:1;margin-left:8px" />
                <el-button text type="danger" size="small" style="margin-left:8px" @click="promqlTemplates.splice(idx,1)">删除</el-button>
              </div>
              <el-button text type="primary" size="small" @click="addPromql">+ 添加 PromQL</el-button>
              <div v-if="promqlTemplates.length === 0" class="filter-hint">
                未配置时，将使用默认系统指标（CPU、内存、磁盘、负载）
              </div>
            </div>
          </el-form-item>
        </template>

        <!-- 通用配置 -->
        <el-divider content-position="left">通用配置</el-divider>
        <el-form-item label="Prompt模板"><el-input v-model="form.prompt_template" placeholder="如: h3c_net_analysis.tpl" /></el-form-item>
        <el-form-item label="默认模型"><el-input v-model="form.model" /></el-form-item>
        <el-form-item label="扫描间隔(秒)"><el-input-number v-model="form.scan_interval_sec" :min="60" /></el-form-item>
        <el-form-item label="关键字匹配"><el-switch v-model="form.keyword_matching" /></el-form-item>
        <el-form-item label="AI异常检测"><el-switch v-model="form.anomaly_detection" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button type="primary" @click="saveSkill">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { skillApi, configApi } from '../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const skills = ref([])
const datasources = ref([])
const showForm = ref(false)
const editId = ref(null)
const form = ref(defaultForm())
const filterLogic = ref('AND')
const filterConditions = ref([])
const availableFields = ref([])
const promqlTemplates = ref([])

/* 操作符选项映射 */
const OPERATOR_MAP = {
  keyword: [
    { value: 'eq', label: '等于 (=)' },
    { value: 'neq', label: '不等于 (≠)' },
    { value: 'in', label: '多值匹配 (in)' },
    { value: 'contains', label: '包含' },
    { value: 'not_contains', label: '不包含' },
  ],
  text: [
    { value: 'eq', label: '等于 (=)' },
    { value: 'neq', label: '不等于 (≠)' },
    { value: 'contains', label: '包含' },
    { value: 'not_contains', label: '不包含' },
  ],
  ip: [
    { value: 'eq', label: '等于 (=)' },
    { value: 'neq', label: '不等于 (≠)' },
    { value: 'cidr', label: '网段匹配 (CIDR)' },
  ],
  number: [
    { value: 'eq', label: '等于 (=)' },
    { value: 'neq', label: '不等于 (≠)' },
    { value: 'gt', label: '大于 (>)' },
    { value: 'gte', label: '大于等于 (≥)' },
    { value: 'lt', label: '小于 (<)' },
    { value: 'lte', label: '小于等于 (≤)' },
  ],
  date: [
    { value: 'gt', label: '晚于 (>)' },
    { value: 'gte', label: '晚于等于 (≥)' },
    { value: 'lt', label: '早于 (<)' },
    { value: 'lte', label: '早于等于 (≤)' },
  ],
}
const NUMERIC_TYPES = new Set(['integer', 'long', 'float', 'double'])

function defaultForm() {
  return {
    skill_name: '', display_name: '', description: '',
    datasource_id: null, ds_type: 'es',
    index_pattern: '', prompt_template: '', model: 'qwen3',
    scan_interval_sec: 300, keyword_matching: true, anomaly_detection: false,
  }
}

const load = async () => {
  try { const r = await skillApi.list(); skills.value = r.data } catch(e) { console.error(e) }
}
const loadDatasources = async () => {
  try { const r = await configApi.listDS(); datasources.value = r.data } catch(e) { console.error(e) }
}
onMounted(() => { load(); loadDatasources() })

/* 数据源切换：自动填充 ds_type */
function onDatasourceChange(dsId) {
  if (!dsId) { return }
  const ds = datasources.value.find(d => d.id === dsId)
  if (ds) {
    form.value.ds_type = ds.ds_type === 'prometheus' ? 'prometheus' : 'es'
  }
}

/* ds_type 手动切换 */
function onDsTypeChange() {
  // 切换类型时清空另一类型的配置
  if (form.value.ds_type === 'prometheus') {
    form.value.index_pattern = ''
    filterConditions.value = []
  } else {
    promqlTemplates.value = []
  }
}

/* Prometheus PromQL 模板操作 */
function addPromql() {
  promqlTemplates.value.push({ name: '', promql: '' })
}

/* 获取 Prometheus 技能的指标摘要 */
function getPromMetricsSummary(row) {
  if (row.query_config && row.query_config.promql_templates) {
    const names = row.query_config.promql_templates.map(t => t.name).filter(n => n)
    return names.length > 0 ? names.slice(0, 3).join(', ') + (names.length > 3 ? '...' : '') : '默认系统指标'
  }
  return '默认系统指标'
}

/* ES 字段相关 */
function parseFields(fieldSchemaStr) {
  if (!fieldSchemaStr) return []
  try {
    const parsed = JSON.parse(fieldSchemaStr)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(f => f.name && f.name.trim())
  } catch { return [] }
}

function getFieldType(fieldName) {
  const f = availableFields.value.find(x => x.name === fieldName)
  return f ? (f.type || 'keyword') : 'keyword'
}

function getOperators(fieldName) {
  const ftype = getFieldType(fieldName)
  if (OPERATOR_MAP[ftype]) return OPERATOR_MAP[ftype]
  if (NUMERIC_TYPES.has(ftype)) return OPERATOR_MAP.number
  return OPERATOR_MAP.keyword
}

function getValuePlaceholder(cond) {
  if (cond.operator === 'in') return '多个值用逗号分隔'
  if (cond.operator === 'cidr') return '如: 192.168.1.0/24'
  if (cond.operator === 'contains' || cond.operator === 'not_contains') return '模糊匹配关键字'
  return '输入匹配值'
}

function onFieldChange(cond) {
  const ops = getOperators(cond.field)
  if (ops.length > 0 && !ops.find(o => o.value === cond.operator)) {
    cond.operator = ops[0].value
  }
  cond.value = ''
}

function addCondition() {
  const firstField = availableFields.value[0]
  const defaultOp = firstField ? (getOperators(firstField.name)[0] || {}).value || 'eq' : 'eq'
  filterConditions.value.push({ field: firstField ? firstField.name : '', operator: defaultOp, value: '' })
}

function removeCondition(idx) {
  filterConditions.value.splice(idx, 1)
}

/* CRUD */
const addSkill = () => {
  editId.value = null
  form.value = defaultForm()
  filterLogic.value = 'AND'
  filterConditions.value = []
  availableFields.value = []
  promqlTemplates.value = []
  showForm.value = true
}

const editSkill = (row) => {
  editId.value = row.id
  form.value = {
    skill_name: row.skill_name, display_name: row.display_name, description: row.description || '',
    datasource_id: row.datasource_id || null, ds_type: row.ds_type || 'es',
    index_pattern: row.index_pattern || '', prompt_template: row.prompt_template, model: row.model,
    scan_interval_sec: row.scan_interval_sec,
    keyword_matching: !!row.keyword_matching, anomaly_detection: !!row.anomaly_detection,
  }
  /* ES: 解析字段列表和过滤条件 */
  availableFields.value = parseFields(row.field_schema)
  if (row.query_filter) {
    try {
      const parsed = JSON.parse(row.query_filter)
      filterLogic.value = parsed.logic || 'AND'
      filterConditions.value = (parsed.conditions || []).map(c => ({
        field: c.field || '', operator: c.operator || 'eq', value: Array.isArray(c.value) ? c.value.join(',') : String(c.value ?? '')
      }))
    } catch {
      filterLogic.value = 'AND'
      filterConditions.value = []
    }
  } else {
    filterLogic.value = 'AND'
    filterConditions.value = []
  }
  /* Prometheus: 解析 query_config */
  if (row.query_config && row.query_config.promql_templates) {
    promqlTemplates.value = row.query_config.promql_templates.map(t => ({ name: t.name || '', promql: t.promql || '' }))
  } else {
    promqlTemplates.value = []
  }
  showForm.value = true
}

const saveSkill = async () => {
  if (!form.value.skill_name || !form.value.display_name || !form.value.prompt_template) {
    ElMessage.warning('请完整填写必填项（技能标识、展示名称、Prompt模板）'); return
  }
  // ES 类型需要索引模式
  if (form.value.ds_type === 'es' && !form.value.index_pattern) {
    ElMessage.warning('ES类型技能必须填写索引模式'); return
  }
  try {
    /* 组装 query_filter (ES) */
    let queryFilter = null
    if (form.value.ds_type === 'es') {
      const validConditions = filterConditions.value
        .filter(c => c.field && c.value !== '' && c.value !== null)
        .map(c => {
          let val = c.value
          if (c.operator === 'in') {
            val = String(c.value).split(',').map(v => v.trim()).filter(v => v)
          }
          return { field: c.field, operator: c.operator, value: val }
        })
      queryFilter = validConditions.length > 0
        ? JSON.stringify({ logic: filterLogic.value, conditions: validConditions })
        : null
    }

    /* 组装 query_config */
    let queryConfig = null
    if (form.value.ds_type === 'prometheus') {
      const validTemplates = promqlTemplates.value.filter(t => t.promql)
      queryConfig = { promql_templates: validTemplates }
    } else if (form.value.ds_type === 'es') {
      queryConfig = { index_pattern: form.value.index_pattern }
    }

    const payload = {
      ...form.value,
      keyword_matching: !!form.value.keyword_matching,
      anomaly_detection: !!form.value.anomaly_detection,
      query_filter: queryFilter,
      query_config: queryConfig,
    }

    if (editId.value) {
      await skillApi.update(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await skillApi.create(payload)
      ElMessage.success('注册成功')
    }
    showForm.value = false; load()
  } catch(e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
}

const delSkill = async (id) => {
  try {
    await ElMessageBox.confirm('确认删除该技能？关联规则可能失效', '提示', { type: 'warning' })
    await skillApi.del(id); ElMessage.success('已删除'); load()
  } catch(e) { /* 取消 */ }
}

const toggleSkill = async (id, val) => {
  try { await skillApi.update(id, { enabled: val }); ElMessage.success(val ? '已启用' : '已禁用'); load() }
  catch(e) { ElMessage.error('操作失败'); load() }
}
</script>

<style scoped>
.cond-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}
.filter-hint {
  color: #909399;
  font-size: 13px;
  padding: 4px 0;
}
</style>
