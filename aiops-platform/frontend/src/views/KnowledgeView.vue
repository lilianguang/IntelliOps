<template>
  <div>
    <h2>知识库</h2>
    <el-card>
      <el-empty description="运维知识库建设中...">
        <template #image>
          <el-icon :size="60" color="#409eff"><Collection /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { Collection } from '@element-plus/icons-vue'
</script>
