<template>
  <el-card>
    <h2>分析报告</h2>
    <p v-if="report">{{ report }}</p>
    <p v-else style="color:#909399">报告ID: {{ $route.params.id }}</p>
  </el-card>
</template>
<script setup>
import { ref } from 'vue'
const report = ref(null)
</script>