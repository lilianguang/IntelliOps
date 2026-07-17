import axios from 'axios'

// 后端API通过Nginx代理（/api/ → backend:8000）
// axios.defaults.baseURL 已在 main.js 中设为 /api，此处不再重复
const BASE = ''

export const authApi = {
  login: (d) => axios.post(`${BASE}/auth/login`, d),
}
export const dashboardApi = {
  getStats: () => axios.get(`${BASE}/ai/dashboard/stats`),
  getRecentEvents: () => axios.get(`${BASE}/ai/dashboard/recent-events`),
  // 告警趋势历史数据（支持日期滑动）
  getAlertTrend: (params) => axios.get(`${BASE}/ai/dashboard/alert-trend`, { params }),
  // AI 运营中心核心指标
  getOperationMetrics: () => axios.get(`${BASE}/ai/dashboard/operation-metrics`),
  // 今日 AI 报告摘要
  getDailySummary: () => axios.get(`${BASE}/ai/reports/daily-summary`),
  // 风险热力图
  getRiskHeatmap: () => axios.get(`${BASE}/ai/dashboard/risk-heatmap`),
}
export const skillApi = {
  list: () => axios.get(`${BASE}/ai/skills`),
  get: (id) => axios.get(`${BASE}/ai/skills/${id}`),
  create: (d) => axios.post(`${BASE}/ai/skills/register`, d),
  update: (id, d) => axios.put(`${BASE}/ai/skills/${id}`, d),
  del: (id) => axios.delete(`${BASE}/ai/skills/${id}`),
  // ES字段说明
  getFields: (id) => axios.get(`${BASE}/ai/skills/${id}/fields`),
  updateFields: (id, fields) => axios.put(`${BASE}/ai/skills/${id}/fields`, { fields }),
}
export const configApi = {
  // 规则
  listRules: (params) => axios.get(`${BASE}/ai/config/rules`, { params }),
  createRule: (d) => axios.post(`${BASE}/ai/config/rules`, d),
  updateRule: (id, d) => axios.put(`${BASE}/ai/config/rules/${id}`, d),
  deleteRule: (id) => axios.delete(`${BASE}/ai/config/rules/${id}`),
  // 数据源
  listDS: () => axios.get(`${BASE}/ai/config/datasources`),
  createDS: (d) => axios.post(`${BASE}/ai/config/datasources`, d),
  updateDS: (id, d) => axios.put(`${BASE}/ai/config/datasources/${id}`, d),
  deleteDS: (id) => axios.delete(`${BASE}/ai/config/datasources/${id}`),
  testDS: (d) => axios.post(`${BASE}/ai/config/datasources/test`, d),
  testDSById: (id) => axios.post(`${BASE}/ai/config/datasources/${id}/test`),
  // 大模型
  listLLMs: () => axios.get(`${BASE}/ai/config/llms`),
  createLLM: (d) => axios.post(`${BASE}/ai/config/llms`, d),
  updateLLM: (id, d) => axios.put(`${BASE}/ai/config/llms/${id}`, d),
  deleteLLM: (id) => axios.delete(`${BASE}/ai/config/llms/${id}`),
  testLLM: (d) => axios.post(`${BASE}/ai/config/llms/test`, d),
  testLLMById: (id) => axios.post(`${BASE}/ai/config/llms/${id}/test`),
  // 告警渠道
  listAlerts: () => axios.get(`${BASE}/ai/config/alerts`),
  createAlert: (d) => axios.post(`${BASE}/ai/config/alerts`, d),
  updateAlert: (id, d) => axios.put(`${BASE}/ai/config/alerts/${id}`, d),
  deleteAlert: (id) => axios.delete(`${BASE}/ai/config/alerts/${id}`),
  testAlert: (d) => axios.post(`${BASE}/ai/config/alerts/test`, d),
  testAlertById: (id) => axios.post(`${BASE}/ai/config/alerts/${id}/test`),
}
export const chatApi = {
  // AI对话涉及ES检索+大模型分析，需要较长超时
  chat: (d) => axios.post(`${BASE}/ai/chat`, d, { timeout: 120000 }),
  /**
   * AI对话 SSE 流式接口 —— 借鉴 SQLBot text/event-stream 消费模式
   * 用 fetch + ReadableStream reader 逐帧读取（EventSource 不支持 POST + Auth header）
   *
   * @param {Object} data - 请求体 { skill, query, time_range, conversation_id }
   * @param {Object} callbacks - { onMeta, onContent, onFinish, onError }
   * @returns {AbortController} 可调用 .abort() 中断生成
   */
  streamChat: (data, callbacks = {}) => {
    const controller = new AbortController()
    const token = localStorage.getItem('token')
    const baseUrl = axios.defaults.baseURL || '/api'

    fetch(`${baseUrl}/ai/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const errText = await resp.text().catch(() => `HTTP ${resp.status}`)
          callbacks.onError?.(errText)
          return
        }
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          // 按 SSE 帧（data:...\n\n）拆分处理
          const frames = buffer.split('\n\n')
          buffer = frames.pop() // 最后一段可能不完整，留存
          for (const frame of frames) {
            const line = frame.trim()
            if (!line.startsWith('data:')) continue
            try {
              const payload = JSON.parse(line.slice(5).trim())
              if (payload.type === 'meta') callbacks.onMeta?.(payload)
              else if (payload.type === 'content') callbacks.onContent?.(payload.content)
              else if (payload.type === 'finish') callbacks.onFinish?.(payload)
              else if (payload.type === 'error') callbacks.onError?.(payload.content)
            } catch { /* 跳过解析异常的帧 */ }
          }
        }
      })
      .catch((e) => {
        if (e.name !== 'AbortError') callbacks.onError?.(e.message)
      })

    return controller
  },
}
export const conversationApi = {
  // 历史对话 / 会话归档
  list: (params) => axios.get(`${BASE}/ai/conversations`, { params }),
  get: (id) => axios.get(`${BASE}/ai/conversations/${id}`),
  archive: (id, archived) => axios.put(`${BASE}/ai/conversations/${id}/archive`, null, { params: { archived } }),
  batchArchive: (ids, archived) => axios.put(`${BASE}/ai/conversations/batch-archive`, { conversation_ids: ids, archived }),
  rename: (id, title) => axios.put(`${BASE}/ai/conversations/${id}/rename`, { title }),
  del: (id) => axios.delete(`${BASE}/ai/conversations/${id}`),
}
export const eventApi = {
  list: (p) => axios.get(`${BASE}/ai/events`, { params: p }),
  get: (id) => axios.get(`${BASE}/ai/events/${id}`),
  devices: () => axios.get(`${BASE}/ai/events/devices`),
  updateStatus: (id, s) => axios.put(`${BASE}/ai/events/${id}/status`, { status: s }),
  batchUpdateStatus: (ids, s) => axios.put(`${BASE}/ai/events/batch/status`, { event_ids: ids, status: s }),
  getStats: () => axios.get(`${BASE}/ai/events/stats`),
  /**
   * 事件 AI 流式分析 SSE 接口
   * @param {string} eventId
   * @param {Object} callbacks - { onMeta, onContent, onFinish, onError }
   * @returns {AbortController}
   */
  analyzeStream: (eventId, callbacks = {}) => {
    const controller = new AbortController()
    const token = localStorage.getItem('token')
    const baseUrl = axios.defaults.baseURL || '/api'

    fetch(`${baseUrl}/ai/events/${eventId}/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({}),
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const errText = await resp.text().catch(() => `HTTP ${resp.status}`)
          callbacks.onError?.(errText)
          return
        }
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const frames = buffer.split('\n\n')
          buffer = frames.pop()
          for (const frame of frames) {
            const line = frame.trim()
            if (!line.startsWith('data:')) continue
            try {
              const payload = JSON.parse(line.slice(5).trim())
              if (payload.type === 'meta') callbacks.onMeta?.(payload)
              else if (payload.type === 'content') callbacks.onContent?.(payload.content)
              else if (payload.type === 'finish') callbacks.onFinish?.(payload)
              else if (payload.type === 'error') callbacks.onError?.(payload.content)
            } catch { /* 跳过解析异常的帧 */ }
          }
        }
      })
      .catch((e) => {
        if (e.name !== 'AbortError') callbacks.onError?.(e.message)
      })

    return controller
  },
}
export const prometheusApi = {
  query: (d) => axios.post(`${BASE}/ai/prometheus/query`, d),
  targets: (dsId) => axios.get(`${BASE}/ai/prometheus/targets`, { params: dsId ? { datasource_id: dsId } : {} }),
  alerts: (dsId) => axios.get(`${BASE}/ai/prometheus/alerts`, { params: dsId ? { datasource_id: dsId } : {} }),
  analyze: (d) => axios.post(`${BASE}/ai/prometheus/analyze`, d),
}
export const userApi = {
  list: () => axios.get(`${BASE}/users/`),
  create: (d) => axios.post(`${BASE}/users/`, d),
  update: (id, d) => axios.put(`${BASE}/users/${id}`, d),
  del: (id) => axios.delete(`${BASE}/users/${id}`),
}
export const cmdbApi = {
  list: (params) => axios.get(`${BASE}/ai/cmdb/assets`, { params }),
  get: (id) => axios.get(`${BASE}/ai/cmdb/assets/${id}`),
  create: (d) => axios.post(`${BASE}/ai/cmdb/assets`, d),
  update: (id, d) => axios.put(`${BASE}/ai/cmdb/assets/${id}`, d),
  del: (id) => axios.delete(`${BASE}/ai/cmdb/assets/${id}`),
  importExcel: (formData) => axios.post(`${BASE}/ai/cmdb/assets/import`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }),
  sync: (d) => axios.post(`${BASE}/ai/cmdb/assets/sync`, d),
  stats: () => axios.get(`${BASE}/ai/cmdb/stats`),
}
export const netinsightApi = {
  listConfigs: (params) => axios.get(`${BASE}/ai/netinsight/configs`, { params }),
  deleteConfig: (id) => axios.delete(`${BASE}/ai/netinsight/configs/${id}`),
  scan: () => axios.post(`${BASE}/ai/netinsight/configs/scan`),
  upload: (formData) => axios.post(`${BASE}/ai/netinsight/configs/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  }),
  getContent: (id) => axios.get(`${BASE}/ai/netinsight/configs/${id}/content`),
  getVersions: (id) => axios.get(`${BASE}/ai/netinsight/configs/${id}/versions`),
  getVersionContent: (id, commit) => axios.get(`${BASE}/ai/netinsight/configs/${id}/versions/${commit}`),
  getSettings: () => axios.get(`${BASE}/ai/netinsight/settings`),
  updateSettings: (d) => axios.put(`${BASE}/ai/netinsight/settings`, d),
  /**
   * AI 配置问答 SSE 流式接口 —— 复用 chatApi.streamChat 的 fetch+ReadableStream 模式
   */
  streamChat: (data, callbacks = {}) => {
    const controller = new AbortController()
    const token = localStorage.getItem('token')
    const baseUrl = axios.defaults.baseURL || '/api'

    fetch(`${baseUrl}/ai/netinsight/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const errText = await resp.text().catch(() => `HTTP ${resp.status}`)
          callbacks.onError?.(errText)
          return
        }
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const frames = buffer.split('\n\n')
          buffer = frames.pop()
          for (const frame of frames) {
            const line = frame.trim()
            if (!line.startsWith('data:')) continue
            try {
              const payload = JSON.parse(line.slice(5).trim())
              if (payload.type === 'meta') callbacks.onMeta?.(payload)
              else if (payload.type === 'content') callbacks.onContent?.(payload.content)
              else if (payload.type === 'finish') callbacks.onFinish?.(payload)
              else if (payload.type === 'error') callbacks.onError?.(payload.content)
            } catch { /* 跳过解析异常的帧 */ }
          }
        }
      })
      .catch((e) => {
        if (e.name !== 'AbortError') callbacks.onError?.(e.message)
      })

    return controller
  },
}

export const logicalApi = {
  // 通用 CRUD (interfaces, ips)
  list: (table, params) => axios.get(`${BASE}/ai/logical/${table}`, { params }),
  create: (table, data) => axios.post(`${BASE}/ai/logical/${table}`, { data }),
  update: (table, id, data) => axios.put(`${BASE}/ai/logical/${table}/${id}`, { data }),
  del: (table, id) => axios.delete(`${BASE}/ai/logical/${table}/${id}`),
  // 通用导出/导入
  exportTable: (table) => axios.get(`${BASE}/ai/logical/${table}/export`, { responseType: 'blob' }),
  importTable: (table, formData) => axios.post(`${BASE}/ai/logical/${table}/import`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
  }),
  // 表元数据
  getMeta: (table) => axios.get(`${BASE}/ai/logical/meta/${table}`),
  createColumn: (table, d) => axios.post(`${BASE}/ai/logical/meta/${table}`, d),
  updateColumn: (table, colId, d) => axios.put(`${BASE}/ai/logical/meta/${table}/${colId}`, d),
  deleteColumn: (table, colId) => axios.delete(`${BASE}/ai/logical/meta/${table}/${colId}`),
  // 业务IP对应关系
  ipMappingList: (params) => axios.get(`${BASE}/ai/logical/ip-mapping`, { params }),
  ipMappingCreate: (d) => axios.post(`${BASE}/ai/logical/ip-mapping`, d),
  ipMappingUpdate: (id, d) => axios.put(`${BASE}/ai/logical/ip-mapping/${id}`, d),
  ipMappingDel: (id) => axios.delete(`${BASE}/ai/logical/ip-mapping/${id}`),
  ipMappingSync: () => axios.post(`${BASE}/ai/logical/ip-mapping/sync`),
  ipMappingExport: () => axios.get(`${BASE}/ai/logical/ip-mapping/export`, { responseType: 'blob' }),
  ipMappingImport: (formData) => axios.post(`${BASE}/ai/logical/ip-mapping/import`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
  }),
  // 负载均衡对应关系
  lbMappingList: (params) => axios.get(`${BASE}/ai/logical/lb-mapping`, { params }),
  lbMappingCreate: (d) => axios.post(`${BASE}/ai/logical/lb-mapping`, d),
  lbMappingUpdate: (id, d) => axios.put(`${BASE}/ai/logical/lb-mapping/${id}`, d),
  lbMappingDel: (id) => axios.delete(`${BASE}/ai/logical/lb-mapping/${id}`),
  lbMappingSync: () => axios.post(`${BASE}/ai/logical/lb-mapping/sync`),
  lbMappingExport: () => axios.get(`${BASE}/ai/logical/lb-mapping/export`, { responseType: 'blob' }),
  lbMappingImport: (formData) => axios.post(`${BASE}/ai/logical/lb-mapping/import`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
  }),
}
export const systemApi = {
  getSettings: () => axios.get(`${BASE}/ai/system/settings`),
  updateSettings: (d) => axios.put(`${BASE}/ai/system/settings`, d),
}
