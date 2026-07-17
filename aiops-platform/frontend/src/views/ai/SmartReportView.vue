<template>
  <div>
    <h2>智能报告</h2>
    <el-card>
      <el-empty description="多模融合分析，生成综合报告">
        <template #image>
          <el-icon :size="60" color="#409eff"><Document /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { Document } from '@element-plus/icons-vue'
</script>
