<template>
  <div>
    <h2>趋势预测</h2>
    <el-card>
      <el-empty description="基于历史数据与AI规划，预测未来趋势与风险">
        <template #image>
          <el-icon :size="60" color="#409eff"><TrendCharts /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { TrendCharts } from '@element-plus/icons-vue'
</script>
