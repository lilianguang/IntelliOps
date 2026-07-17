<template>
  <div class="login-container">
    <el-card class="login-card">
      <h2>AIOPS 智能运维平台</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" size="large" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" style="width:100%" :loading="loading" @click="doLogin">登 录</el-button>
        </el-form-item>
      </el-form>
      <div v-if="error" style="color:#f56c6c;text-align:center;margin-top:10px">{{ error }}</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '../../api/index.js'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const error = ref('')
const form = reactive({ username: 'admin', password: 'admin123' })
const rules = { username: [{ required: true, message: '请输入用户名' }], password: [{ required: true, message: '请输入密码' }] }

const doLogin = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true; error.value = ''
    try {
      const res = await authApi.login(form)
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('user', JSON.stringify({ username: res.data.username, role: res.data.role }))
      router.push('/dashboard')
    } catch (e) {
      error.value = e.response?.data?.detail || '登录失败'
    } finally { loading.value = false }
  })
}
</script>

<style scoped>
.login-container { display:flex; justify-content:center; align-items:center; min-height:100vh; background:linear-gradient(135deg,#667eea,#764ba2); }
.login-card { width:400px; }
h2 { text-align:center; margin-bottom:30px; color:#303133; }
</style>