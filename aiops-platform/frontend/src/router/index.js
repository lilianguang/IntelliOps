import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/login/LoginView.vue') },
  {
    path: '/',
    component: () => import('../components/layout/MainLayout.vue'),
    redirect: '/aiops-center',
    children: [
      // AI 运营中心（首页）
      { path: 'aiops-center', component: () => import('../views/DashboardView.vue') },
      { path: 'dashboard', redirect: '/aiops-center' },

      // AI 智能中心
      { path: 'ai-center', component: () => import('../views/AICenterView.vue') },
      { path: 'ai-center/assistant', component: () => import('../views/AIAssistantView.vue') },
      { path: 'ai-center/reports', component: () => import('../views/AIReportsView.vue') },
      { path: 'ai-center/prediction', component: () => import('../views/AIPredictionView.vue') },
      { path: 'ai-center/diagnosis', component: () => import('../views/AIDiagnosisView.vue') },
      { path: 'chat', redirect: '/ai-center/assistant' },

      // 事件中心
      { path: 'events', component: () => import('../views/EventCenterView.vue') },
      { path: 'events/realtime', component: () => import('../views/EventCenterView.vue') },
      { path: 'events/history', component: () => import('../views/EventCenterView.vue') },
      { path: 'events/analysis', component: () => import('../views/events/EventsAnalysisView.vue') },
      { path: 'events/statistics', component: () => import('../views/events/EventsStatisticsView.vue') },

      { path: 'netinsight', component: () => import('../views/NetInsightView.vue') },
      { path: 'report/:id', component: () => import('../views/ReportView.vue') },
      { path: 'knowledge', component: () => import('../views/KnowledgeView.vue') },

      // 资源中心（实际页面仍使用原 admin 路径，菜单仅做聚合）
      { path: 'admin/cmdb', component: () => import('../views/admin/CMDBView.vue') },
      { path: 'admin/logical/ip-mapping', component: () => import('../views/admin/logical/IpMappingView.vue') },
      { path: 'admin/logical/lb', component: () => import('../views/admin/logical/LBView.vue') },
      {
        path: 'admin/logical/:table',
        component: () => import('../views/admin/logical/LogicalTableView.vue'),
        props: true,
      },

      // 配置中心
      { path: 'admin/skills', component: () => import('../views/admin/SkillManageView.vue') },
      { path: 'admin/rules', component: () => import('../views/admin/RuleManageView.vue') },
      { path: 'admin/datasources', component: () => import('../views/admin/DatasourceView.vue') },
      { path: 'admin/llm', component: () => import('../views/admin/LLMConfigView.vue') },
      { path: 'admin/alerts', component: () => import('../views/admin/AlertConfigView.vue') },
      { path: 'admin/users', component: () => import('../views/admin/UserManageView.vue') },
      // 系统管理
      { path: 'admin/system', component: () => import('../views/admin/system/SystemManageView.vue') },
      { path: 'admin/system/site', component: () => import('../views/admin/system/SiteSettingsView.vue') },
      { path: 'admin/system/theme', component: () => import('../views/admin/system/ThemeSettingsView.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', component: () => import('../views/errors/404.vue') },
]

export default createRouter({ history: createWebHistory(), routes })
