<template><router-view /></template>

<script setup>
import { onMounted } from 'vue'
import { systemApi } from './api/index.js'

const applySite = (site) => {
  if (site?.name) document.title = site.name
  if (site?.favicon) {
    let link = document.querySelector('link[rel="icon"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = site.favicon
  }
}

const applyTheme = (theme) => {
  if (!theme) return
  const root = document.documentElement
  if (theme.primaryColor) {
    root.style.setProperty('--el-color-primary', theme.primaryColor)
  }
  if (theme.backgroundColor) {
    root.style.setProperty('--app-background-color', theme.backgroundColor)
  }
  if (theme.sidebarColor) {
    root.style.setProperty('--app-sidebar-color', theme.sidebarColor)
  }
}

onMounted(() => {
  systemApi.getSettings()
    .then((r) => {
      const { site, theme } = r.data || {}
      applySite(site)
      applyTheme(theme)
    })
    .catch(() => {})
})
</script>
