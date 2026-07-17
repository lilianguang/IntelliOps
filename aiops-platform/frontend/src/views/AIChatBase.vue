<template>
  <div style="display:flex;gap:10px;height:calc(100vh - 120px)">
    <!-- 历史对话侧栏 -->
    <el-card style="width:280px;display:flex;flex-direction:column" body-style="flex:1;overflow:hidden;padding:0">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span>历史对话</span>
          <el-radio-group v-model="archivedFilter" size="small" @change="loadHistory(true)">
            <el-radio-button :label="0">活跃</el-radio-button>
            <el-radio-button :label="1">已归档</el-radio-button>
          </el-radio-group>
        </div>
        <div style="margin-top:6px;display:flex;align-items:center;gap:6px">
          <el-checkbox v-model="filterBySkill" size="small" @change="loadHistory(true)">仅当前技能</el-checkbox>
          <el-tag v-if="filterBySkill && skill" size="small" type="info">{{ currentSkillLabel }}</el-tag>
        </div>
      </template>
      <div style="padding:8px;border-bottom:1px solid #eee">
        <el-input v-model="historyKw" placeholder="搜索历史对话..." size="small" clearable @keyup.enter="loadHistory(true)" @clear="loadHistory(true)">
          <template #append><el-button @click="loadHistory(true)">搜</el-button></template>
        </el-input>
      </div>
      <div style="flex:1;overflow-y:auto">
        <div v-for="c in history" :key="c.conversation_id"
             class="hist-item" :class="{active: activeId === c.conversation_id}"
             @click="viewHistory(c)">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <el-text v-if="editingId !== c.conversation_id" truncated style="font-weight:600;flex:1" @dblclick.stop="startRename(c)">{{ c.title || c.query?.slice(0,18) || 'AI对话' }}</el-text>
            <el-input v-else v-model="editTitle" size="small" style="flex:1" @keyup.enter="confirmRename(c)" @blur="confirmRename(c)" @click.stop autofocus />
            <el-tag v-if="c.archived" type="info" size="small">归档</el-tag>
          </div>
          <div class="hist-meta">
            <span>{{ c.skill }}</span>
            <span>{{ (c.created_at||'').substring(0,16) }}</span>
          </div>
          <div class="hist-actions" @click.stop>
            <el-button text size="small" type="primary" @click="startRename(c)">重命名</el-button>
            <el-button text size="small" :type="c.archived ? 'success' : 'warning'" @click="toggleArchive(c)">
              {{ c.archived ? '取消归档' : '归档' }}
            </el-button>
            <el-button text size="small" type="danger" @click="delConv(c)">删除</el-button>
          </div>
        </div>
        <el-empty v-if="!history.length" description="暂无历史对话" :image-size="60" />
      </div>
      <div style="padding:8px;border-top:1px solid #eee;text-align:center">
        <el-button size="small" @click="newChat">+ 新对话</el-button>
      </div>
    </el-card>

    <!-- 对话主区 -->
    <el-card style="flex:1;display:flex;flex-direction:column" body-style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <div style="display:flex;gap:10px;margin-bottom:15px;align-items:center;flex-wrap:wrap">
        <el-select v-model="skill" placeholder="选择技能" style="width:200px" @change="onSkillChange">
          <el-option v-for="s in skills" :key="s.skill_name" :label="s.display_name" :value="s.skill_name" />
        </el-select>
        <el-select v-model="timeRange" style="width:150px">
          <el-option label="最近5分钟" value="5m" />
          <el-option label="最近30分钟" value="30m" />
          <el-option label="最近1小时" value="1h" />
          <el-option label="最近6小时" value="6h" />
          <el-option label="最近24小时" value="24h" />
        </el-select>
        <el-button text type="primary" @click="showFields = !showFields" :disabled="!skill">
          📋 字段说明{{ skillFields.length ? ` (${skillFields.length})` : '' }}
        </el-button>
      </div>

      <!-- ES字段说明面板 -->
      <el-collapse-transition>
        <div v-show="showFields && skillFields.length" style="margin-bottom:15px">
          <el-card shadow="never" body-style="padding:10px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span style="font-weight:600;color:#409eff">ES 索引字段说明</span>
              <el-button text size="small" @click="showFields = false">收起</el-button>
            </div>
            <el-table :data="skillFields" size="small" max-height="240" border>
              <el-table-column prop="name" label="字段名" width="150">
                <template #default="{row}"><code style="color:#e6a23c">{{ row.name }}</code></template>
              </el-table-column>
              <el-table-column prop="type" label="类型" width="90" />
              <el-table-column prop="desc" label="含义" min-width="200" show-overflow-tooltip />
              <el-table-column prop="example" label="示例" min-width="150" show-overflow-tooltip>
                <template #default="{row}"><span style="color:#909399;font-size:12px">{{ row.example }}</span></template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-collapse-transition>

      <!-- 消息列表 -->
      <div ref="msgBox" class="msg-list">
        <div v-for="(msg,i) in messages" :key="i" class="msg-item">
          <!-- 用户消息 -->
          <div v-if="msg.role==='user'" class="msg-user">
            <el-tag type="info" size="small">你</el-tag>
            <div class="bubble-user">{{ msg.content }}</div>
          </div>
          <!-- AI 消息（Markdown 渲染） -->
          <div v-else class="msg-ai">
            <el-tag type="success" size="small">AI</el-tag>
            <div v-if="msg.risk" style="margin:5px 0">
              <el-tag :type="riskTag(msg.risk)" size="small">{{ msg.risk }}</el-tag>
            </div>
            <div class="bubble-ai markdown-body" v-html="msg.html || renderMd(msg.content)"></div>
          </div>
        </div>

        <!-- 欢迎面板 -->
        <div v-if="showWelcome" class="welcome-panel">
          <!-- 普通 AI 助手模式：完整面板 -->
          <template v-if="!props.capability">
            <div class="quick-questions">
              <div class="section-title">快速提问</div>
              <div class="quick-btns">
                <el-button round size="small" @click="quickAsk('近24小时告警趋势')">近24小时告警趋势</el-button>
                <el-button round size="small" @click="quickAsk('哪些设备告警最多')">哪些设备告警最多</el-button>
                <el-button round size="small" @click="quickAsk('P1告警根因分析')">P1告警根因分析</el-button>
                <el-button round size="small" @click="quickAsk('网络设备健康状态')">网络设备健康状态</el-button>
              </div>
            </div>

            <div class="capability-section">
              <div class="section-title">智能运维能力</div>
              <div class="capability-grid">
                <div v-for="cap in capabilities" :key="cap.title" class="capability-card" @click="openSkillDialog(cap)">
                  <div class="cap-icon" :style="{ background: cap.bg }">
                    <el-icon :size="22" :color="cap.color"><component :is="cap.icon" /></el-icon>
                  </div>
                  <div class="cap-info">
                    <div class="cap-title">{{ cap.title }}</div>
                    <div class="cap-desc">{{ cap.desc }}</div>
                  </div>
                  <el-tag v-if="cap.badge" size="small" type="danger" class="cap-badge">{{ cap.badge }}</el-tag>
                </div>
              </div>
            </div>
          </template>

          <!-- 单能力模式：只显示对应能力 -->
          <template v-else>
            <div class="single-capability">
              <div class="cap-icon-large" :style="{ background: currentCapability?.bg }">
                <el-icon :size="48" :color="currentCapability?.color"><component :is="currentCapability?.icon" /></el-icon>
              </div>
              <div class="single-cap-title">{{ pageTitle }}</div>
              <div class="single-cap-desc">{{ currentCapability?.desc }}</div>
              <el-button type="primary" size="large" @click="openSkillDialog(currentCapability)">开始分析</el-button>
            </div>
          </template>
        </div>

        <!-- 流式加载光标 -->
        <div v-if="streaming" class="msg-item">
          <div class="msg-ai">
            <el-tag type="success" size="small">AI</el-tag>
            <span class="cursor-blink">▋</span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div style="display:flex;gap:10px">
        <el-input
          v-model="query"
          placeholder="输入你的问题..."
          @keyup.enter="doChat"
          clearable
          :disabled="streaming"
        />
        <el-button v-if="!streaming" type="primary" @click="doChat" :loading="false">发送</el-button>
        <el-button v-else type="danger" @click="stopStream">停止</el-button>
      </div>
    </el-card>
  </div>

  <!-- 技能选择弹窗（点击能力卡片时弹出） -->
  <el-dialog v-model="skillDialogVisible" :title="currentCap?.title || '选择技能'" width="520px" :close-on-click-modal="false">
    <div v-if="currentCap" style="margin-bottom:16px">
      <el-alert :title="currentCap.desc" type="info" :closable="false" show-icon />
    </div>
    <div style="margin-bottom:12px;color:#606266;font-size:14px">
      选择一个或多个技能进行 AI 分析（可多选，支持联合分析）：
    </div>
    <el-select
      v-model="dialogSelectedSkills"
      multiple
      filterable
      placeholder="请选择技能"
      style="width:100%"
    >
      <el-option
        v-for="s in skills"
        :key="s.skill_name"
        :label="s.display_name"
        :value="s.skill_name"
      />
    </el-select>
    <div v-if="dialogSelectedSkills.length > 1" style="margin-top:12px">
      <el-tag type="success" size="small">多技能联合分析模式</el-tag>
      <span style="margin-left:8px;color:#909399;font-size:13px">将合并多个数据源进行关联分析</span>
    </div>

    <!-- 时间范围选择 -->
    <div style="margin-top:18px;margin-bottom:8px;color:#606266;font-size:14px;font-weight:600">时间范围：</div>
    <el-radio-group v-model="dialogTimeRange" style="display:flex;flex-direction:column;gap:10px">
      <el-radio label="24h">最近 24 小时</el-radio>
      <el-radio label="7d">最近一周</el-radio>
      <el-radio label="custom">自定义时间</el-radio>
    </el-radio-group>
    <el-date-picker
      v-if="dialogTimeRange === 'custom'"
      v-model="dialogCustomRange"
      type="datetimerange"
      range-separator="至"
      start-placeholder="开始时间"
      end-placeholder="结束时间"
      format="YYYY-MM-DD HH:mm:ss"
      value-format="YYYY-MM-DD HH:mm:ss"
      style="width:100%;margin-top:12px"
    />

    <template #footer>
      <el-button @click="skillDialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="dialogSelectedSkills.length === 0 || (dialogTimeRange === 'custom' && (!dialogCustomRange || dialogCustomRange.length !== 2))" @click="confirmSkillDialog">开始分析</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted, nextTick, computed, markRaw } from 'vue'
import MarkdownIt from 'markdown-it'
import { skillApi, chatApi, conversationApi } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Aim, TrendCharts, Monitor, MagicStick } from '@element-plus/icons-vue'

// ---- props ----
const props = defineProps({
  capability: { type: String, default: null } // null | 'reports' | 'prediction' | 'diagnosis'
})

// ---- markdown-it 初始化 ----
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})
const renderMd = (text) => md.render(text || '')

// 响应式状态
const skills = ref([])
const skill = ref('')
const query = ref('')
const timeRange = ref('30m')
const messages = ref([{ role: 'ai', content: '你好！我是 AIOps 智能运维助手，请选择技能并输入你的问题。' }])
const streaming = ref(false)
const msgBox = ref(null)
let streamController = null

// 是否显示欢迎面板（仅初始状态）
const showWelcome = computed(() => messages.value.length <= 1 && !streaming.value)

// 智能运维能力卡片
const capabilities = [
  { title: '智能报告', desc: '多模融合分析，生成综合报告', icon: markRaw(Document), color: '#409eff', bg: '#ecf5ff', badge: 'NEW', prompt: '生成今天的智能运维综合报告' },
  { title: '根因分析', desc: '基于拓扑与告警关联，快速定位故障根源', icon: markRaw(Aim), color: '#409eff', bg: '#ecf5ff', badge: 'NEW', prompt: '对最近的严重告警进行根因分析' },
  { title: '趋势预测', desc: '基于历史数据与AI规划，预测未来趋势与风险', icon: markRaw(TrendCharts), color: '#67c23a', bg: '#f0f9eb', badge: 'NEW', prompt: '预测未来24小时的告警趋势' },
  { title: '批量诊断', desc: '批量执行诊断命令，提升运维效率', icon: markRaw(Monitor), color: '#9b59b6', bg: '#f3e8ff', badge: 'NEW', prompt: '批量诊断所有核心设备的健康状态' },
  { title: '异常检测', desc: '智能检测异常模式，提前发现潜在风险', icon: markRaw(MagicStick), color: '#e6a23c', bg: '#fdf6ec', badge: 'NEW', prompt: '检测最近的异常事件模式' },
]

// 当前指定能力
const currentCapability = computed(() => {
  if (!props.capability) return null
  const capMap = {
    reports: capabilities[0],     // 智能报告
    prediction: capabilities[2],  // 趋势预测
    diagnosis: capabilities[3],   // 批量诊断
  }
  return capMap[props.capability]
})

// 页面标题
const pageTitle = computed(() => {
  const titles = {
    reports: 'AI报告',
    prediction: 'AI预测',
    diagnosis: 'AI诊断',
  }
  return titles[props.capability] || 'AI助手'
})

// 快速提问：填充输入框并自动发送
const quickAsk = (text) => {
  query.value = text
  doChat()
}

// 技能选择弹窗（点击能力卡片时弹出）
const skillDialogVisible = ref(false)
const currentCap = ref(null)
const dialogSelectedSkills = ref([])
const dialogTimeRange = ref('24h')
const dialogCustomRange = ref(null)

// 打开技能选择弹窗，默认选中当前技能
const openSkillDialog = (cap) => {
  currentCap.value = cap
  dialogSelectedSkills.value = skill.value ? [skill.value] : []
  dialogTimeRange.value = '24h'
  dialogCustomRange.value = null
  skillDialogVisible.value = true
}

// 确认技能选择后开始分析
const confirmSkillDialog = () => {
  if (dialogSelectedSkills.value.length === 0) return
  skillDialogVisible.value = false
  query.value = currentCap.value?.prompt || '请进行智能分析'
  const opts = { timeRange: dialogTimeRange.value === 'custom' ? 'custom' : dialogTimeRange.value }
  if (dialogTimeRange.value === 'custom' && dialogCustomRange.value && dialogCustomRange.value.length === 2) {
    opts.startTime = dialogCustomRange.value[0]
    opts.endTime = dialogCustomRange.value[1]
  }
  if (dialogTimeRange.value !== 'custom') {
    timeRange.value = dialogTimeRange.value
  }
  doChat(dialogSelectedSkills.value, opts)
}

// ES字段说明
const showFields = ref(false)
const skillFields = ref([])
const onSkillChange = async () => {
  skillFields.value = []
  if (!skill.value) return
  const s = skills.value.find(x => x.skill_name === skill.value)
  if (!s) return
  try {
    const res = await skillApi.getFields(s.id)
    skillFields.value = res.data || []
  } catch { /* 字段说明加载失败，忽略 */ }
  loadHistory()
}

// 历史对话
const history = ref([])
const archivedFilter = ref(0)
const historyKw = ref('')
const activeId = ref(null)
const filterBySkill = ref(true)
const editingId = ref(null)
const editTitle = ref('')

// 当前选中技能的显示名称
const currentSkillLabel = computed(() => {
  const s = skills.value.find(x => x.skill_name === skill.value)
  return s ? s.display_name : skill.value
})

const riskTag = (l) => ({ low:'info', medium:'warning', high:'danger', critical:'danger' }[l]||'info')

// 自动滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

const loadHistory = async () => {
  try {
    const params = { archived: archivedFilter.value, page: 1, page_size: 50 }
    if (historyKw.value) params.keyword = historyKw.value
    if (filterBySkill.value && skill.value) params.skill = skill.value
    const res = await conversationApi.list(params)
    history.value = res.data?.items || []
  } catch (e) { console.error('历史加载失败', e) }
}

const viewHistory = async (c) => {
  try {
    const res = await conversationApi.get(c.conversation_id)
    const d = res.data
    activeId.value = c.conversation_id
    if (Array.isArray(d.messages) && d.messages.length) {
      messages.value = d.messages.map(m => ({
        role: m.role === 'assistant' ? 'ai' : m.role,
        content: m.content,
        risk: m.risk_level,
        created_at: m.created_at,
      }))
    } else {
      messages.value = [
        { role: 'user', content: d.query },
        { role: 'ai', content: d.full_report?.content || d.summary || '无返回', risk: d.risk_level },
      ]
    }
    if (d.skill) skill.value = d.skill
    scrollToBottom()
  } catch (e) { ElMessage.error('加载对话失败') }
}

const toggleArchive = async (c) => {
  try {
    await conversationApi.archive(c.conversation_id, c.archived ? 0 : 1)
    ElMessage.success(c.archived ? '已取消归档' : '已归档')
    loadHistory()
  } catch { ElMessage.error('操作失败') }
}

const delConv = async (c) => {
  try {
    await ElMessageBox.confirm('确认删除该对话？', '提示', { type: 'warning' })
    await conversationApi.del(c.conversation_id)
    ElMessage.success('已删除')
    if (activeId.value === c.conversation_id) newChat()
    loadHistory()
  } catch { /* 取消 */ }
}

// 重命名功能
const startRename = (c) => {
  editingId.value = c.conversation_id
  editTitle.value = c.title || c.query?.slice(0, 30) || ''
}
const confirmRename = async (c) => {
  const title = editTitle.value.trim()
  editingId.value = null
  if (!title || title === (c.title || c.query?.slice(0, 30))) return
  try {
    await conversationApi.rename(c.conversation_id, title)
    c.title = title
    ElMessage.success('已重命名')
  } catch { ElMessage.error('重命名失败') }
}

const newChat = () => {
  activeId.value = null
  messages.value = [{ role: 'ai', content: '你好！我是 AIOps 智能运维助手，请选择技能并输入你的问题。' }]
}

// ---- 核心：SSE 流式对话 ----
const doChat = async (skillList = null, opts = {}) => {
  const validSkillList = Array.isArray(skillList) ? skillList : null
  const skillsToSend = validSkillList || (skill.value ? [skill.value] : [])

  if (!query.value.trim() || streaming.value) return
  if (skillsToSend.length === 0) {
    ElMessage.warning('请先选择技能')
    return
  }

  const userMsg = query.value
  messages.value.push({ role: 'user', content: userMsg })
  const aiIdx = messages.value.push({ role: 'ai', content: '', html: '' }) - 1
  streaming.value = true
  query.value = ''
  scrollToBottom()

  const effectiveTimeRange = opts.timeRange || timeRange.value
  const payload = { query: userMsg, time_range: effectiveTimeRange === 'custom' ? '24h' : effectiveTimeRange }
  if (opts.startTime) payload.start_time = opts.startTime
  if (opts.endTime) payload.end_time = opts.endTime
  if (skillsToSend.length === 1) {
    payload.skill = skillsToSend[0]
  } else {
    payload.skills = skillsToSend
  }
  if (activeId.value) payload.conversation_id = activeId.value

  streamController = chatApi.streamChat(payload, {
    onMeta: (data) => {
      activeId.value = data.conversation_id
    },
    onContent: (chunk) => {
      messages.value[aiIdx].content += chunk
      messages.value[aiIdx].html = renderMd(messages.value[aiIdx].content)
      scrollToBottom()
    },
    onFinish: (data) => {
      messages.value[aiIdx].risk = data.risk_level
      streaming.value = false
      streamController = null
      loadHistory()
    },
    onError: (errMsg) => {
      messages.value[aiIdx].content = '❌ ' + (errMsg || '请求失败')
      messages.value[aiIdx].html = renderMd(messages.value[aiIdx].content)
      streaming.value = false
      streamController = null
    },
  })
}

// 停止生成
const stopStream = () => {
  if (streamController) {
    streamController.abort()
    streamController = null
  }
  streaming.value = false
}

onMounted(async () => {
  try {
    const res = await skillApi.list()
    skills.value = res.data
    if (skills.value.length) {
      skill.value = skills.value[0].skill_name
      await onSkillChange()
    }
  } catch(e) { console.error(e) }
  loadHistory()

  // 若指定了单一能力（AI报告/AI预测/AI诊断），自动打开对应能力弹窗
  if (props.capability && currentCapability.value) {
    openSkillDialog(currentCapability.value)
  }
})
</script>

<style scoped>
.msg-list {
  flex:1; overflow-y:auto;
  border:1px solid #dcdfe6; border-radius:4px;
  padding:15px; margin-bottom:15px; background:#fafafa;
}
.msg-item { margin-bottom:15px; }
.msg-user { text-align:right; }
.bubble-user {
  display:inline-block; background:#409eff; color:#fff;
  padding:8px 12px; border-radius:8px; margin-top:5px;
  max-width:80%; text-align:left; white-space:pre-wrap;
}
.msg-ai { text-align:left; }
.bubble-ai {
  background:#fff; padding:12px; border-radius:8px; margin-top:5px;
  border:1px solid #e8e8e8; max-width:90%;
  line-height:1.7; font-size:14px;
}
.bubble-ai :deep(h1),
.bubble-ai :deep(h2),
.bubble-ai :deep(h3) { margin:10px 0 6px; }
.bubble-ai :deep(table) { border-collapse:collapse; width:100%; margin:8px 0; }
.bubble-ai :deep(th),
.bubble-ai :deep(td) { border:1px solid #ddd; padding:6px 10px; text-align:left; }
.bubble-ai :deep(th) { background:#f5f7fa; font-weight:600; }
.bubble-ai :deep(code) { background:#f0f0f0; padding:2px 4px; border-radius:3px; font-size:13px; }
.bubble-ai :deep(pre) { background:#282c34; color:#abb2bf; padding:12px; border-radius:6px; overflow-x:auto; margin:8px 0; }
.bubble-ai :deep(pre code) { background:none; padding:0; color:inherit; }
.bubble-ai :deep(ul),
.bubble-ai :deep(ol) { padding-left:20px; margin:6px 0; }
.bubble-ai :deep(blockquote) { border-left:4px solid #409eff; padding-left:12px; color:#606266; margin:8px 0; }
.cursor-blink { animation:blink 1s infinite; color:#409eff; font-size:16px; margin-left:4px; }
@keyframes blink { 0%,50%{opacity:1} 51%,100%{opacity:0} }
.hist-item { padding:10px 12px; border-bottom:1px solid #f0f0f0; cursor:pointer; transition:background .2s; }
.hist-item:hover { background:#f5f7fa; }
.hist-item.active { background:#ecf5ff; border-left:3px solid #409eff; }
.hist-meta { display:flex; justify-content:space-between; color:#909399; font-size:12px; margin-top:4px; }
.hist-actions { margin-top:4px; }

/* 欢迎面板 */
.welcome-panel { padding:10px 0; }
.section-title { font-size:14px; font-weight:600; color:#303133; margin-bottom:12px; }
.quick-btns { display:flex; flex-wrap:wrap; gap:8px; }
.capability-section { margin-top:20px; }
.capability-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:12px; }
.capability-card {
  display:flex; align-items:flex-start; gap:10px;
  padding:14px; border-radius:8px; border:1px solid #ebeef5;
  background:#fff; cursor:pointer; transition:all .2s;
  position:relative; overflow:hidden;
}
.capability-card:hover { box-shadow:0 2px 12px rgba(0,0,0,.1); transform:translateY(-2px); border-color:#c6e2ff; }
.cap-icon { width:40px; height:40px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.cap-info { flex:1; min-width:0; }
.cap-title { font-size:14px; font-weight:600; color:#303133; margin-bottom:4px; }
.cap-desc { font-size:12px; color:#909399; line-height:1.5; }
.cap-badge { position:absolute; top:8px; right:8px; transform:scale(0.8); }

/* 单能力模式 */
.single-capability {
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  min-height:320px; text-align:center;
}
.cap-icon-large { width:80px; height:80px; border-radius:16px; display:flex; align-items:center; justify-content:center; margin-bottom:20px; }
.single-cap-title { font-size:24px; font-weight:600; color:#303133; margin-bottom:12px; }
.single-cap-desc { font-size:14px; color:#606266; max-width:480px; margin-bottom:24px; line-height:1.6; }
</style>
