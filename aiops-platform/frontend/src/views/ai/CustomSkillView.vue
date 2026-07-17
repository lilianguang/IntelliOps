<template>
  <div>
    <h2>自定义技能</h2>
    <el-card>
      <el-empty description="自定义分析技能与模板，满足个性化需求">
        <template #image>
          <el-icon :size="60" color="#409eff"><MagicStick /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { MagicStick } from '@element-plus/icons-vue'
</script>
