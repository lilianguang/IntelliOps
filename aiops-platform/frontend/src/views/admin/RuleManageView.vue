<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2>规则配置</h2>
      <el-button type="primary" @click="addRule">新增规则</el-button>
    </div>
    <el-table :data="rules" stripe style="width:100%">
      <el-table-column prop="rule_name" label="规则名称" min-width="150" />
      <el-table-column label="关联技能" width="160">
        <template #default="{row}">
          <el-tag size="small" :type="skillMap[row.skill_id] ? '' : 'danger'">
            {{ skillMap[row.skill_id] ? skillMap[row.skill_id].display_name : `技能#${row.skill_id}(未配置)` }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="rule_type" label="类型" width="140">
        <template #default="{row}">{{ typeMap[row.rule_type] || row.rule_type }}</template>
      </el-table-column>
      <el-table-column prop="risk_level" label="风险等级" width="100">
        <template #default="{row}"><el-tag :type="riskTag(row.risk_level)" size="small">{{ row.risk_level }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="80" />
      <el-table-column label="启用" width="80">
        <template #default="{row}"><el-switch :model-value="!!row.enabled" disabled /></template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{row}">
          <el-button text type="primary" size="small" @click="editRule(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="delRule(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showForm" :title="editId?'编辑规则':'新增规则'" width="780px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="规则名称"><el-input v-model="form.rule_name" /></el-form-item>
        <el-form-item label="关联技能">
          <el-select v-model="form.skill_id" style="width:100%" placeholder="请选择关联技能">
            <el-option v-for="s in skills" :key="s.id" :label="`${s.display_name} (${s.skill_name})`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则类型">
          <el-select v-model="form.rule_type" style="width:100%" @change="onTypeChange">
            <el-option v-for="(v,k) in typeMap" :key="k" :label="v" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="form.risk_level">
            <el-option label="低" value="low" /><el-option label="中" value="medium" />
            <el-option label="高" value="high" /><el-option label="严重" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" /></el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>

        <!-- ========== 匹配条件 ========== -->
        <el-form-item label="匹配条件">
          <div style="width:100%">
            <el-radio-group v-model="advancedMode" size="small" style="margin-bottom:10px">
              <el-radio-button :value="false">表单模式</el-radio-button>
              <el-radio-button :value="true">JSON高级模式</el-radio-button>
            </el-radio-group>

            <!-- JSON 高级模式 -->
            <el-input v-if="advancedMode" v-model="matchStr" type="textarea" :rows="6" placeholder="JSON格式的匹配条件" />

            <!-- 表单模式 -->
            <div v-else>
              <!-- 危险命令: ES查询构建器 -->
              <template v-if="form.rule_type === 'dangerous_command'">
                <div style="margin-bottom:8px">
                  <el-radio-group v-model="esLogic" size="small">
                    <el-radio-button value="should">满足任意条件 (OR)</el-radio-button>
                    <el-radio-button value="must">满足全部条件 (AND)</el-radio-button>
                  </el-radio-group>
                </div>
                <div v-for="(cond, i) in esConditions" :key="i" class="cond-row">
                  <el-input v-model="cond.field" placeholder="字段名(如:command)" style="width:150px" />
                  <el-select v-model="cond.type" style="width:120px" placeholder="匹配方式">
                    <el-option label="通配符匹配" value="wildcard" />
                    <el-option label="精确匹配" value="term" />
                    <el-option label="数值范围" value="range" />
                  </el-select>
                  <template v-if="cond.type === 'range'">
                    <el-input v-model="cond.min" placeholder="最小值" style="width:90px" />
                    <span style="color:#999">~</span>
                    <el-input v-model="cond.max" placeholder="最大值" style="width:90px" />
                  </template>
                  <template v-else>
                    <el-input v-model="cond.value" placeholder="值(通配符用*)" style="width:160px" />
                  </template>
                  <el-button text type="danger" size="small" @click="esConditions.splice(i,1)" :icon="Delete" />
                </div>
                <el-button text type="primary" size="small" @click="addEsCondition">+ 添加匹配条件</el-button>
              </template>

              <!-- 关键字/命令监控/忽略规则: 支持多简单条件 -->
              <template v-else-if="['keyword_match','command_monitor','ignore_rule'].includes(form.rule_type)">
                <div style="margin-bottom:8px">
                  <el-radio-group v-model="simpleLogic" size="small">
                    <el-radio-button value="OR">满足任意条件 (OR)</el-radio-button>
                    <el-radio-button value="AND">满足全部条件 (AND)</el-radio-button>
                  </el-radio-group>
                </div>
                <div v-for="(cond, i) in simpleMatches" :key="i" class="cond-row">
                  <el-input v-model="cond.field" placeholder="字段名(如:command)" style="width:160px" />
                  <el-select v-model="cond.operator" style="width:120px">
                    <el-option label="包含" value="contains" />
                    <el-option label="等于" value="equals" />
                    <el-option label="开头是" value="startswith" />
                    <el-option label="正则匹配" value="regex" />
                  </el-select>
                  <el-input v-model="cond.value" placeholder="匹配值" style="width:180px" />
                  <el-button text type="danger" size="small" @click="simpleMatches.splice(i,1)" :icon="Delete" />
                </div>
                <el-button text type="primary" size="small" @click="addSimpleMatch">+ 添加匹配条件</el-button>
              </template>

              <!-- 日志级别/HTTP状态码/响应时间: 支持多数值比较 -->
              <template v-else-if="['severity_filter','http_status_alert','response_time_alert'].includes(form.rule_type)">
                <div style="margin-bottom:8px">
                  <el-radio-group v-model="simpleLogic" size="small">
                    <el-radio-button value="OR">满足任意条件 (OR)</el-radio-button>
                    <el-radio-button value="AND">满足全部条件 (AND)</el-radio-button>
                  </el-radio-group>
                </div>
                <div v-for="(cond, i) in simpleMatches" :key="i" class="cond-row">
                  <el-input v-model="cond.field" :placeholder="numericFieldHint" style="width:160px" />
                  <el-select v-model="cond.operator" style="width:100px">
                    <el-option label="≥" value=">=" />
                    <el-option label="＞" value=">" />
                    <el-option label="＝" value="==" />
                    <el-option label="＜" value="<" />
                    <el-option label="≤" value="<=" />
                  </el-select>
                  <el-input-number v-model="cond.value" :placeholder="'数值'" style="width:160px" />
                  <el-button text type="danger" size="small" @click="simpleMatches.splice(i,1)" :icon="Delete" />
                </div>
                <el-button text type="primary" size="small" @click="addSimpleMatch">+ 添加匹配条件</el-button>
              </template>

              <!-- Prometheus 指标阈值: 支持多指标条件，指标名从技能 PromQL 模板中选择 -->
              <template v-else-if="form.rule_type === 'metric_threshold'">
                <div style="margin-bottom:8px">
                  <el-radio-group v-model="metricLogic" size="small">
                    <el-radio-button value="OR">满足任意条件 (OR)</el-radio-button>
                    <el-radio-button value="AND">满足全部条件 (AND)</el-radio-button>
                  </el-radio-group>
                </div>
                <div v-for="(cond, i) in metricMatches" :key="i" class="cond-row" style="align-items:flex-start;flex-wrap:wrap">
                  <el-select v-model="cond.metric" placeholder="选择指标（来自技能 PromQL 模板）" style="width:240px" filterable allow-create>
                    <el-option v-for="m in skillMetricOptions" :key="m.name" :label="`${m.label} (${m.name})`" :value="m.name" />
                  </el-select>
                  <el-select v-model="cond.operator" style="width:100px">
                    <el-option label="＞" value=">" />
                    <el-option label="≥" value=">=" />
                    <el-option label="＜" value="<" />
                    <el-option label="≤" value="<=" />
                    <el-option label="＝" value="==" />
                    <el-option label="≠" value="!=" />
                  </el-select>
                  <el-input-number v-model="cond.value" :precision="2" placeholder="阈值" style="width:130px" />
                  <el-input v-model="cond.instance_filter" placeholder="实例过滤(可选，如:10.0.*)" style="width:180px" />
                  <el-button text type="danger" size="small" @click="metricMatches.splice(i,1)" :icon="Delete" />
                </div>
                <el-button text type="primary" size="small" @click="addMetricMatch">+ 添加指标条件</el-button>
                <div v-if="!skillMetricOptions.length" style="color:#e6a23c;font-size:12px;margin-top:6px">
                  当前技能未配置 PromQL 查询模板，可手动输入指标名。
                </div>
              </template>

              <!-- 其他类型: JSON回退 -->
              <template v-else>
                <el-input v-model="matchStr" type="textarea" :rows="4" placeholder="JSON格式" />
              </template>
            </div>
          </div>
        </el-form-item>

        <!-- ========== 频率阈值（可选） ========== -->
        <el-form-item label="频率阈值">
          <div style="width:100%">
            <el-switch v-model="thresholdEnabled" active-text="启用" inactive-text="不限制" style="margin-bottom:8px" />
            <div v-if="thresholdEnabled" class="cond-row" style="margin-top:8px">
              <el-input-number v-model="thresholdForm.window_minutes" :min="1" :max="1440" style="width:120px" />
              <span>分钟内出现</span>
              <el-input-number v-model="thresholdForm.count" :min="2" :max="10000" style="width:120px" />
              <span>次触发告警</span>
            </div>
            <div v-if="thresholdEnabled" style="color:#909399;font-size:12px;margin-top:4px">
              仅当匹配条件在指定时间窗口内累计达到指定次数时，才触发告警动作
            </div>
          </div>
        </el-form-item>

        <!-- ========== 排除条件 ========== -->
        <el-form-item label="排除条件">
          <div style="width:100%">
            <el-radio-group v-model="excludeAdvanced" size="small" style="margin-bottom:10px">
              <el-radio-button :value="false">表单模式</el-radio-button>
              <el-radio-button :value="true">JSON高级模式</el-radio-button>
            </el-radio-group>

            <el-input v-if="excludeAdvanced" v-model="excludeStr" type="textarea" :rows="3" placeholder="JSON格式(可选)" />

            <div v-else>
              <div v-for="(ex, i) in excludeConditions" :key="i" class="cond-row">
                <el-input v-model="ex.field" placeholder="字段名" style="width:150px" />
                <el-select v-model="ex.operator" style="width:110px">
                  <el-option label="等于" value="equals" />
                  <el-option label="包含" value="contains" />
                  <el-option label="不等于" value="not_equals" />
                  <el-option label="不包含" value="not_contains" />
                </el-select>
                <el-input v-model="ex.value" placeholder="值" style="width:160px" />
                <el-button text type="danger" size="small" @click="excludeConditions.splice(i,1)" :icon="Delete" />
              </div>
              <el-button text type="primary" size="small" @click="excludeConditions.push({field:'',operator:'equals',value:''})">+ 添加排除条件</el-button>
            </div>
          </div>
        </el-form-item>

        <!-- ========== 动作配置 ========== -->
        <el-form-item label="动作配置">
          <div style="width:100%">
            <el-radio-group v-model="actionAdvanced" size="small" style="margin-bottom:10px">
              <el-radio-button :value="false">表单模式</el-radio-button>
              <el-radio-button :value="true">JSON高级模式</el-radio-button>
            </el-radio-group>

            <el-input v-if="actionAdvanced" v-model="actionStr" type="textarea" :rows="4" placeholder='{"alert":true,"alert_type":"immediate"}' />

            <div v-else>
              <el-checkbox v-model="actionForm.alert">触发告警</el-checkbox>
              <el-checkbox v-model="actionForm.call_ai">AI分析</el-checkbox>
              <div v-if="actionForm.call_ai" class="ai-context-box">
                <el-checkbox v-model="aiContextEnabled">联合上下文分析（拉取同设备近期多条日志做关联分析，适用于日志级别 0-3 等场景）</el-checkbox>
                <div v-if="aiContextEnabled" class="ai-context-params">
                  <span class="ai-context-label">时间窗</span>
                  <el-input-number v-model="aiContextForm.window_minutes" :min="1" :max="1440" size="small" style="width:110px" />
                  <span class="ai-context-label">分钟，最多</span>
                  <el-input-number v-model="aiContextForm.max_logs" :min="5" :max="500" size="small" style="width:110px" />
                  <span class="ai-context-label">条</span>
                  <el-checkbox v-model="aiContextForm.same_device_only">仅同设备</el-checkbox>
                  <el-checkbox v-model="aiContextForm.on_new_event_only">仅首次事件分析(省Token)</el-checkbox>
                </div>
              </div>
              <div v-if="actionForm.alert" style="margin-top:8px">
                <el-select v-model="actionForm.alert_type" style="width:200px" placeholder="告警类型">
                  <el-option label="即时告警" value="immediate" />
                  <el-option label="周期告警" value="periodic" />
                </el-select>
              </div>
              <div v-if="actionForm.alert" style="margin-top:8px">
                <el-select v-model="alertChannelIds" multiple clearable style="width:100%" placeholder="选择告警渠道（空则发送给所有启用渠道）">
                  <el-option v-for="ch in alertChannels" :key="ch.id" :label="`${ch.name} (${{dingtalk:'钉钉',email:'邮件',webhook:'Webhook'}[ch.channel_type] || ch.channel_type})`" :value="ch.id" />
                </el-select>
                <div style="color:#909399;font-size:12px;margin-top:4px">不选择时，默认向所有已启用的告警渠道发送</div>
              </div>
            </div>
          </div>
        </el-form-item>

        <!-- ========== 告警模板（可选自定义） ========== -->
        <el-form-item v-if="actionForm.alert" label="告警模板">
          <div style="width:100%">
            <el-switch v-model="alertTemplateEnabled" active-text="自定义" inactive-text="使用默认" style="margin-bottom:8px" />
            <div v-if="alertTemplateEnabled">
              <el-input v-model="alertTemplate" type="textarea" :rows="6"
                placeholder="支持 {变量名} 替换，如：&#10;**[{rule_name}] 告警**&#10;> 告警级别：{risk_level}&#10;- 设备：{device_ip}&#10;- 详情：{message}&#10;- 风险分析：{risk_analysis}" />
              <div class="tpl-example">
                <div class="tpl-example-head">
                  <span>💡 「{{ typeMap[form.rule_type] || form.rule_type }}」规则模板样例（不同规则类型字段不同）</span>
                  <el-button text type="primary" size="small" @click="applyTemplateExample">填入此样例</el-button>
                </div>
                <pre class="tpl-example-body">{{ currentTemplateExample }}</pre>
              </div>
              <div style="color:#909399;font-size:12px;margin-top:6px">
                <b>可用变量：</b><br>
                {rule_name}=规则名, {risk_level}=告警级别, {threshold}=阈值(指标规则)<br>
                <b>时间字段：</b>{timestamp}=触发时间(东八区 YYYY-MM-DD HH:mm:ss), {@timestamp}=原始ISO时间<br>
                <b>CMDB资产字段：</b>{device_name}=设备名称, {region}=区域, {datacenter}=机房, {owner}=负责人, {asset_type}=资产类型, {organization}=组织归属<br>
                <b>AI分析字段：</b>{ai_analysis}=AI风险分析摘要, {risk_analysis}=同{ai_analysis}（需开启“AI分析”，危险命令规则会自动使用命令分析模板）<br>
                <b>日志字段：</b>{log_type}, {hostname}, {topic}, {domain}, {device_ip}, {status}, {responsetime},
                {request}, {client}, {user}, {src_ip}, {command}, {message}, {severity}, {module},
                {metric_name}, {metric_value}, {instance}, {job} 等<br>
                <b>Markdown加粗：</b>标题加粗请使用 <code>**标题**</code>（**与文字之间不要加空格），例如 <code>**网络设备-危险命令告警**</code><br>
                <span style="color:#E6A23C">区域来源：优先从CMDB资产管理按IP查询；CMDB无区域时，业务日志的 topic 会自动映射为区域（如 nginx-access-log-8ov→政务外网、nginx-access-log-int→互联网）</span>
              </div>
            </div>
            <div v-else style="color:#909399;font-size:12px">
              将根据规则类型自动使用内置模板（不同规则类型有不同的默认格式）
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm=false">取消</el-button>
        <el-button type="primary" @click="saveRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { configApi, skillApi } from '../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const rules = ref([]); const skills = ref([]); const alertChannels = ref([]); const showForm = ref(false); const editId = ref(null)
const form = ref(defaultForm())

// 高级模式开关
const advancedMode = ref(false)
const excludeAdvanced = ref(false)
const actionAdvanced = ref(false)

// JSON 字符串（高级模式用）
const matchStr = ref(''); const actionStr = ref(''); const excludeStr = ref('')

// 表单模式数据模型
const esConditions = ref([])       // [{field,type,value,min,max}]
const esLogic = ref('should')      // should | must
const simpleMatches = ref([])      // [{field,operator,value}]  支持多条件
const simpleLogic = ref('OR')      // AND | OR
const metricMatches = ref([])      // [{metric,operator,value,instance_filter}] 支持多指标条件
const metricLogic = ref('OR')      // AND | OR
const skillMetricOptions = ref([]) // 当前技能中定义的 PromQL 指标名列表 [{name,label}]
const excludeConditions = ref([])  // [{field,operator,value}]
const actionForm = ref({ alert:true, call_ai:false, alert_type:'immediate' })
const alertChannelIds = ref([]) // 规则关联的告警渠道ID列表
const thresholdEnabled = ref(false)
const thresholdForm = ref({ window_minutes: 5, count: 10 })
const alertTemplateEnabled = ref(false)
const alertTemplate = ref('')
const aiContextEnabled = ref(false)
const aiContextForm = ref({ window_minutes: 10, max_logs: 50, same_device_only: true, on_new_event_only: true })

const skillMap = computed(() => Object.fromEntries(skills.value.map(s => [s.id, s])))
const typeMap = {
  severity_filter:'日志级别过滤', command_monitor:'命令监控', dangerous_command:'危险命令',
  http_status_alert:'HTTP状态码', response_time_alert:'响应超时',
  keyword_match:'关键字匹配', ignore_rule:'忽略规则',
  metric_threshold:'指标阈值(Prometheus)'
}
const riskTag = (l) => ({ low:'info', medium:'warning', high:'danger', critical:'danger' }[l]||'info')

const numericFieldHint = computed(() => {
  const hints = {
    severity_filter: '字段名(如:severity)',
    http_status_alert: '字段名(如:status)',
    response_time_alert: '字段名(如:responsetime)',
  }
  return hints[form.value.rule_type] || '字段名'
})

// 各规则类型的告警模板样例（随规则类型动态变化，供参考/一键填入）
const TEMPLATE_EXAMPLES = {
  dangerous_command: `🚨 **[{rule_name}] 危险命令告警**

> 告警级别：{risk_level}
> 告警时间：{timestamp}

- 设备IP：{device_ip}
- 操作用户：{user}
- 来源IP：{src_ip}
- 执行命令：{command}

**AI 分析**
{ai_analysis}`,
  command_monitor: `📝 **[{rule_name}] 命令监控告警**

> 告警级别：{risk_level}
> 告警时间：{timestamp}

- 设备IP：{device_ip}
- 操作用户：{user}
- 来源IP：{src_ip}
- 执行命令：{command}`,
  severity_filter: `⚠️ **[{rule_name}] 日志级别告警**

> 告警级别：{risk_level}
> 告警时间：{timestamp}

- 设备IP：{device_ip}
- 日志级别：{severity}
- 模块：{module}
- 详情：{message}`,
  http_status_alert: `🔥 **[{rule_name}] HTTP状态告警**

> 告警级别：{risk_level}

- 业务区域：{region}
- 域名：{domain}
- 请求接口：{request}
- 状态码：{status}
- 客户端IP：{client}`,
  response_time_alert: `⏱️ **[{rule_name}] 响应超时告警**

> 告警级别：{risk_level}

- 业务区域：{region}
- 域名：{domain}
- 请求接口：{request}
- 响应时间：{responsetime}s
- 客户端IP：{client}`,
  keyword_match: `🔍 **[{rule_name}] 关键字匹配告警**

> 告警级别：{risk_level}

- 设备IP：{device_ip}
- 主机名：{hostname}
- 匹配内容：{message}`,
  metric_threshold: `🌐 **[{rule_name}] 指标阈值告警**

> 告警级别：{risk_level}
> 告警时间：{timestamp}

**触发指标**
- 指标名：{metric_name}
- 当前值：{metric_value}
- 触发阈值：{operator} {threshold}

**设备信息**
- 设备名称：{device_name}
- 设备IP：{device_ip}
- 实例：{instance}
- 所属区域：{region}
- 负责人：{owner}

**AI 分析**
{ai_analysis}`,
}

const FALLBACK_EXAMPLE = `🔔 **[{rule_name}] 告警**

> 告警级别：{risk_level}
> 告警时间：{timestamp}

- 设备：{device_ip}
- 详情：{message}`

const currentTemplateExample = computed(() => TEMPLATE_EXAMPLES[form.value.rule_type] || FALLBACK_EXAMPLE)

const applyTemplateExample = async () => {
  if (alertTemplate.value.trim()) {
    try {
      await ElMessageBox.confirm('将用当前规则类型的样例覆盖已填写的模板内容，是否继续？', '提示', { type: 'warning' })
    } catch { return }
  }
  alertTemplate.value = currentTemplateExample.value
}

function defaultForm() {
  return { rule_name:'', rule_type:'dangerous_command', risk_level:'medium', priority:10, skill_id:null,
    match_condition:{}, exclude_condition:null, action_config:{alert:true}, enabled:true }
}

// ---- 表单模式 <-> JSON 转换 ----

/** 解析 es_query 的单个条件为表单行 */
function parseEsCondition(cond) {
  if (cond.wildcard) {
    const [field, value] = Object.entries(cond.wildcard)[0]
    return { field, type:'wildcard', value }
  }
  if (cond.term) {
    const [field, value] = Object.entries(cond.term)[0]
    return { field, type:'term', value }
  }
  if (cond.range) {
    const [field, ranges] = Object.entries(cond.range)[0]
    return { field, type:'range', value:'', min:ranges.gte??'', max:ranges.lte??'' }
  }
  return { field:'', type:'wildcard', value:'' }
}

/** 将表单行转为 es_query 条件 */
function buildEsCondition(c) {
  if (c.type === 'wildcard') return { wildcard: { [c.field]: c.value } }
  if (c.type === 'term') return { term: { [c.field]: c.value } }
  if (c.type === 'range') {
    const r = {}
    if (c.min !== '' && c.min != null) r.gte = Number(c.min)
    if (c.max !== '' && c.max != null) r.lte = Number(c.max)
    return { range: { [c.field]: r } }
  }
  return {}
}

/** 当切换规则类型时，初始化/重置表单模型 */
function onTypeChange() {
  const t = form.value.rule_type
  if (t === 'dangerous_command') {
    if (!esConditions.value.length) {
      esConditions.value = [{ field:'command', type:'wildcard', value:'*' }]
    }
  } else if (['keyword_match','command_monitor','ignore_rule'].includes(t)) {
    if (!simpleMatches.value.length) {
      simpleMatches.value = [{ field:'command', operator:'contains', value:'' }]
    }
  } else if (['severity_filter','http_status_alert','response_time_alert'].includes(t)) {
    const defaults = {
      severity_filter: { field:'severity', operator:'<=', value:3 },
      http_status_alert: { field:'status', operator:'>=', value:500 },
      response_time_alert: { field:'responsetime', operator:'>', value:1000 },
    }
    simpleMatches.value = [{ ...defaults[t] }]
  } else if (t === 'metric_threshold') {
    if (!metricMatches.value.length) {
      metricMatches.value = [{ metric:'', operator:'>', value:90, instance_filter:'' }]
    }
    loadSkillMetrics()
  }
}

/** 从已有的 match_condition JSON 填充表单（兼容旧版单条件 + 新版多条件） */
function fillMatchForm(matchCondition) {
  const t = form.value.rule_type
  if (t === 'dangerous_command') {
    const boolQ = matchCondition?.es_query?.bool || {}
    if (boolQ.should && Array.isArray(boolQ.should)) {
      esLogic.value = 'should'
      esConditions.value = boolQ.should.map(parseEsCondition)
    } else if (boolQ.must && Array.isArray(boolQ.must)) {
      esLogic.value = 'must'
      esConditions.value = boolQ.must.map(parseEsCondition)
    } else {
      esLogic.value = 'should'
      esConditions.value = [{ field:'command', type:'wildcard', value:'*' }]
    }
  } else if (['keyword_match','command_monitor','ignore_rule'].includes(t)) {
    simpleLogic.value = matchCondition?.logic || 'OR'
    const conds = matchCondition?.conditions
    if (Array.isArray(conds) && conds.length) {
      simpleMatches.value = conds.map(c => ({
        field: c.field || 'command',
        operator: c.operator || 'contains',
        value: c.value ?? '',
      }))
    } else if (matchCondition?.field) {
      // 兼容旧版单条件
      simpleMatches.value = [{
        field: matchCondition.field || 'command',
        operator: matchCondition.operator || 'contains',
        value: matchCondition.value ?? '',
      }]
    } else {
      simpleMatches.value = [{ field:'command', operator:'contains', value:'' }]
    }
  } else if (['severity_filter','http_status_alert','response_time_alert'].includes(t)) {
    simpleLogic.value = matchCondition?.logic || 'OR'
    const defaults = {
      severity_filter: { field:'severity', operator:'<=', value:3 },
      http_status_alert: { field:'status', operator:'>=', value:500 },
      response_time_alert: { field:'responsetime', operator:'>', value:1000 },
    }
    const conds = matchCondition?.conditions
    if (Array.isArray(conds) && conds.length) {
      simpleMatches.value = conds.map(c => ({
        field: c.field || defaults[t].field,
        operator: c.operator || '>=',
        value: c.value ?? 0,
      }))
    } else if (matchCondition?.field) {
      // 兼容旧版单条件
      simpleMatches.value = [{
        field: matchCondition.field || defaults[t].field,
        operator: matchCondition.operator || '>=',
        value: matchCondition.value ?? 0,
      }]
    } else {
      simpleMatches.value = [{ ...defaults[t] }]
    }
  } else if (t === 'metric_threshold') {
    metricLogic.value = matchCondition?.logic || 'OR'
    const conds = matchCondition?.conditions
    if (Array.isArray(conds) && conds.length) {
      metricMatches.value = conds.map(c => ({
        metric: c.metric || '',
        operator: c.operator || '>',
        value: c.value ?? 90,
        instance_filter: c.instance_filter || '',
      }))
    } else if (matchCondition?.metric) {
      // 兼容旧版单条件
      metricMatches.value = [{
        metric: matchCondition.metric || '',
        operator: matchCondition.operator || '>',
        value: matchCondition.value ?? 90,
        instance_filter: matchCondition.instance_filter || '',
      }]
    } else {
      metricMatches.value = [{ metric:'', operator:'>', value:90, instance_filter:'' }]
    }
    loadSkillMetrics()
  }
  // 解析频率阈值
  const threshold = matchCondition?.threshold
  if (threshold && threshold.count) {
    thresholdEnabled.value = true
    thresholdForm.value = { window_minutes: threshold.window_minutes || 5, count: threshold.count || 10 }
  } else {
    thresholdEnabled.value = false
    thresholdForm.value = { window_minutes: 5, count: 10 }
  }
}

/** 从表单构建 match_condition JSON（支持多条件数组 + 逻辑关系） */
function buildMatchJson() {
  const t = form.value.rule_type
  let result = {}
  if (t === 'dangerous_command') {
    const conds = esConditions.value.filter(c => c.field && (c.value || c.type==='range')).map(buildEsCondition)
    result = { es_query: { bool: { [esLogic.value]: conds } } }
  } else if (['keyword_match','command_monitor','ignore_rule'].includes(t)) {
    const valid = simpleMatches.value.filter(c => c.field && c.value !== '')
    if (valid.length === 1) {
      // 单条件保持扁平结构（最大兼容）
      result = { field: valid[0].field, operator: valid[0].operator, value: valid[0].value }
    } else if (valid.length > 1) {
      result = { logic: simpleLogic.value, conditions: valid.map(c => ({ field:c.field, operator:c.operator, value:c.value })) }
    }
  } else if (['severity_filter','http_status_alert','response_time_alert'].includes(t)) {
    const valid = simpleMatches.value.filter(c => c.field && c.value !== '')
    if (valid.length === 1) {
      result = { field: valid[0].field, operator: valid[0].operator, value: Number(valid[0].value) || 0 }
    } else if (valid.length > 1) {
      result = { logic: simpleLogic.value, conditions: valid.map(c => ({ field:c.field, operator:c.operator, value: Number(c.value) || 0 })) }
    }
  } else if (t === 'metric_threshold') {
    const valid = metricMatches.value.filter(c => c.metric && c.value !== '')
    if (valid.length === 1) {
      result = {
        metric: valid[0].metric,
        operator: valid[0].operator,
        value: Number(valid[0].value) || 0,
      }
      if (valid[0].instance_filter) result.instance_filter = valid[0].instance_filter
    } else if (valid.length > 1) {
      result = {
        logic: metricLogic.value,
        conditions: valid.map(c => {
          const item = { metric: c.metric, operator: c.operator, value: Number(c.value) || 0 }
          if (c.instance_filter) item.instance_filter = c.instance_filter
          return item
        })
      }
    }
  } else {
    // 回退: 解析 JSON 字符串
    try { result = JSON.parse(matchStr.value) } catch { result = {} }
  }
  // 附加频率阈值（可选）
  if (thresholdEnabled.value) {
    result.threshold = { count: thresholdForm.value.count, window_minutes: thresholdForm.value.window_minutes }
  }
  return result
}

/** 从已有的 exclude_condition JSON 填充表单 */
function fillExcludeForm(excludeCondition) {
  if (!excludeCondition) {
    excludeConditions.value = []
    return
  }
  // 多条件格式: {conditions: [{field, operator, value}, ...]}
  if (excludeCondition.conditions && Array.isArray(excludeCondition.conditions)) {
    excludeConditions.value = excludeCondition.conditions.map(c => ({
      field: c.field || '',
      operator: c.operator || 'equals',
      value: c.value ?? '',
    }))
  } else if (excludeCondition.field) {
    // 简单字段格式: {field, operator, value}
    excludeConditions.value = [{
      field: excludeCondition.field,
      operator: excludeCondition.operator || 'equals',
      value: excludeCondition.value ?? '',
    }]
  } else {
    // 无法解析的格式，切到高级模式
    excludeAdvanced.value = true
    excludeStr.value = JSON.stringify(excludeCondition, null, 2)
    excludeConditions.value = []
  }
}

/** 从表单构建 exclude_condition JSON */
function buildExcludeJson() {
  if (excludeAdvanced.value) {
    return excludeStr.value.trim() ? JSON.parse(excludeStr.value) : null
  }
  const valid = excludeConditions.value.filter(e => e.field && e.value !== '')
  if (!valid.length) return null
  if (valid.length === 1) {
    return { field: valid[0].field, operator: valid[0].operator, value: valid[0].value }
  }
  // 多条件: 用 conditions 数组包装在 dict 中（后端 Pydantic 要求 dict 类型）
  return { conditions: valid.map(e => ({ field: e.field, operator: e.operator, value: e.value })) }
}

/** 从已有的 action_config JSON 填充表单 */
function fillActionForm(actionConfig) {
  actionForm.value = {
    alert: !!actionConfig?.alert,
    call_ai: !!actionConfig?.call_ai,
    alert_type: actionConfig?.alert_type || 'immediate',
  }
  // 关联告警渠道
  const channels = actionConfig?.alert_channels
  alertChannelIds.value = Array.isArray(channels) ? channels.map(id => Number(id)) : []
  // 告警模板
  const tpl = actionConfig?.alert_template || ''
  alertTemplateEnabled.value = !!tpl
  alertTemplate.value = tpl
  // 联合上下文分析
  const aiCtx = actionConfig?.ai_context
  aiContextEnabled.value = actionConfig?.ai_analysis === 'context_correlation' && (aiCtx?.enabled !== false)
  aiContextForm.value = {
    window_minutes: aiCtx?.window_minutes ?? 10,
    max_logs: aiCtx?.max_logs ?? 50,
    same_device_only: aiCtx?.same_device_only ?? true,
    on_new_event_only: aiCtx?.on_new_event_only ?? true,
  }
}

/** 从表单构建 action_config JSON */
function buildActionJson() {
  if (actionAdvanced.value) {
    return actionStr.value.trim() ? JSON.parse(actionStr.value) : {}
  }
  const cfg = { alert: actionForm.value.alert }
  if (actionForm.value.call_ai) cfg.call_ai = true
  if (actionForm.value.alert) cfg.alert_type = actionForm.value.alert_type
  // 关联告警渠道
  if (actionForm.value.alert && alertChannelIds.value.length > 0) {
    cfg.alert_channels = alertChannelIds.value.map(id => Number(id))
  }
  // 自定义告警模板
  if (actionForm.value.alert && alertTemplateEnabled.value && alertTemplate.value.trim()) {
    cfg.alert_template = alertTemplate.value.trim()
  }
  // 联合上下文分析
  if (actionForm.value.call_ai && aiContextEnabled.value) {
    cfg.ai_analysis = 'context_correlation'
    cfg.ai_context = {
      enabled: true,
      window_minutes: Number(aiContextForm.value.window_minutes) || 10,
      max_logs: Number(aiContextForm.value.max_logs) || 50,
      same_device_only: !!aiContextForm.value.same_device_only,
      on_new_event_only: !!aiContextForm.value.on_new_event_only,
    }
  }
  return cfg
}

function addEsCondition() {
  esConditions.value.push({ field:'', type:'wildcard', value:'*' })
}

function addSimpleMatch() {
  simpleMatches.value.push({ field:'', operator:'contains', value:'' })
}

function addMetricMatch() {
  metricMatches.value.push({ metric:'', operator:'>', value:90, instance_filter:'' })
}

/** 加载当前技能中定义的 PromQL 指标名列表（用于指标阈值规则） */
async function loadSkillMetrics() {
  const skillId = form.value.skill_id
  if (!skillId) {
    skillMetricOptions.value = []
    return
  }
  try {
    const res = await skillApi.get(skillId)
    const skill = res.data
    const promqlTemplates = skill?.query_config?.promql_templates || []
    const metrics = skill?.query_config?.metrics || []
    const options = []
    promqlTemplates.forEach(t => {
      const name = typeof t === 'string' ? t : (t.name || '')
      const promql = typeof t === 'string' ? t : (t.promql || '')
      if (name) {
        options.push({ name, label: name, promql })
      }
    })
    metrics.forEach(m => {
      const name = typeof m === 'string' ? m : (m.name || '')
      if (name && !options.find(o => o.name === name)) {
        options.push({ name, label: name })
      }
    })
    skillMetricOptions.value = options
  } catch (e) {
    console.error('加载技能指标失败', e)
    skillMetricOptions.value = []
  }
}

const load = async () => {
  try {
    const [rr, sr, ar] = await Promise.all([configApi.listRules(), skillApi.list(), configApi.listAlerts()])
    rules.value = rr.data
    skills.value = sr.data
    alertChannels.value = ar.data || []
    if (skills.value.length && !form.value.skill_id) form.value.skill_id = skills.value[0].id
  } catch(e) { console.error(e) }
}
onMounted(load)

// 监听关联技能变化：指标阈值规则需要重新加载技能定义的 PromQL 指标名
watch(() => form.value.skill_id, () => {
  if (form.value.rule_type === 'metric_threshold') {
    loadSkillMetrics()
  }
})

const addRule = () => {
  form.value = defaultForm()
  if (skills.value.length) form.value.skill_id = skills.value[0].id
  advancedMode.value = false; excludeAdvanced.value = false; actionAdvanced.value = false
  matchStr.value = '{}'; actionStr.value = JSON.stringify({alert:true}, null, 2); excludeStr.value = ''
  esConditions.value = [{ field:'command', type:'wildcard', value:'*' }]
  esLogic.value = 'should'
  simpleMatches.value = [{ field:'command', operator:'contains', value:'' }]
  simpleLogic.value = 'OR'
  metricMatches.value = [{ metric:'', operator:'>', value:90, instance_filter:'' }]
  metricLogic.value = 'OR'
  skillMetricOptions.value = []
  excludeConditions.value = []
  actionForm.value = { alert:true, call_ai:false, alert_type:'immediate' }
  alertChannelIds.value = []
  thresholdEnabled.value = false
  thresholdForm.value = { window_minutes: 5, count: 10 }
  alertTemplateEnabled.value = false
  alertTemplate.value = ''
  aiContextEnabled.value = false
  aiContextForm.value = { window_minutes: 10, max_logs: 50, same_device_only: true, on_new_event_only: true }
  onTypeChange()
  showForm.value = true
}

const editRule = (row) => {
  editId.value = row.id
  form.value = { ...defaultForm(), ...row, enabled: !!row.enabled }
  advancedMode.value = false; excludeAdvanced.value = false; actionAdvanced.value = false

  // 重置数组，避免旧数据残留
  esConditions.value = []; simpleMatches.value = []; metricMatches.value = []; skillMetricOptions.value = []

  // 尝试用表单模式解析，失败则回退高级模式
  try {
    fillMatchForm(row.match_condition || {})
    matchStr.value = JSON.stringify(row.match_condition || {}, null, 2)
  } catch {
    advancedMode.value = true
    matchStr.value = JSON.stringify(row.match_condition || {}, null, 2)
  }

  try {
    fillExcludeForm(row.exclude_condition)
    if (!excludeAdvanced.value) excludeStr.value = row.exclude_condition ? JSON.stringify(row.exclude_condition, null, 2) : ''
  } catch {
    excludeAdvanced.value = true
    excludeStr.value = row.exclude_condition ? JSON.stringify(row.exclude_condition, null, 2) : ''
  }

  try {
    fillActionForm(row.action_config || {})
    actionStr.value = JSON.stringify(row.action_config || {}, null, 2)
  } catch {
    actionAdvanced.value = true
    actionStr.value = JSON.stringify(row.action_config || {}, null, 2)
  }

  showForm.value = true
}

const saveRule = async () => {
  if (!form.value.skill_id) { ElMessage.warning('请选择关联技能'); return }
  try {
    // 构建最终 JSON
    let matchCondition, excludeCondition, actionConfig
    if (advancedMode.value) {
      matchCondition = matchStr.value.trim() ? JSON.parse(matchStr.value) : {}
    } else {
      matchCondition = buildMatchJson()
    }
    excludeCondition = buildExcludeJson()
    if (actionAdvanced.value) {
      actionConfig = actionStr.value.trim() ? JSON.parse(actionStr.value) : {}
    } else {
      actionConfig = buildActionJson()
    }

    const payload = { ...form.value, enabled: !!form.value.enabled,
      match_condition: matchCondition, exclude_condition: excludeCondition, action_config: actionConfig }
    if (editId.value) await configApi.updateRule(editId.value, payload)
    else await configApi.createRule(payload)
    ElMessage.success(editId.value ? '更新成功' : '创建成功')
    showForm.value = false; load()
  } catch(e) {
    const detail = e.response?.data?.detail
    let msg = typeof detail === 'string' ? detail : (e.message || '未知错误')
    if (Array.isArray(detail)) {
      msg = detail.map(d => d.msg || JSON.stringify(d)).join('; ')
    }
    ElMessage.error('保存失败: ' + msg)
  }
}

const delRule = async (id) => {
  try {
    await ElMessageBox.confirm('确认删除该规则？', '提示', { type:'warning' })
    await configApi.deleteRule(id); ElMessage.success('已删除'); load()
  } catch(e) { /* 取消 */ }
}
</script>

<style scoped>
.cond-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.tpl-example {
  margin-top: 10px;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  background: #fafafa;
  overflow: hidden;
}
.tpl-example-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: #f0f2f5;
  font-size: 12px;
  color: #606266;
}
.tpl-example-body {
  margin: 0;
  padding: 10px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
}
.ai-context-box {
  margin-top: 8px;
  padding: 8px 10px;
  background: #f5f7fa;
  border-radius: 6px;
}
.ai-context-params {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.ai-context-label {
  font-size: 13px;
  color: #606266;
}
</style>
