<template>
  <div>
    <h2>批量诊断</h2>
    <el-card>
      <el-empty description="批量执行诊断命令，提升运维效率">
        <template #image>
          <el-icon :size="60" color="#409eff"><Monitor /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { Monitor } from '@element-plus/icons-vue'
</script>
