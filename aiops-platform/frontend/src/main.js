import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import axios from 'axios'

axios.defaults.baseURL = import.meta.env.VITE_API_BASE || '/api'
axios.defaults.timeout = 30000

axios.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

axios.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      router.push('/login')
    }
    return Promise.reject(err)
  }
)

const app = createApp(App)
for (const [key, c] of Object.entries(ElementPlusIconsVue)) app.component(key, c)
app.use(ElementPlus).use(router).use(createPinia()).mount('#app')