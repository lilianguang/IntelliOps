<template>
  <div>
    <h2>根因分析</h2>
    <el-card>
      <el-empty description="基于拓扑与告警关联分析，快速定位故障根源">
        <template #image>
          <el-icon :size="60" color="#409eff"><Aim /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { Aim } from '@element-plus/icons-vue'
</script>
