<template>
  <div>
    <h2>用户管理</h2>
    <div style="margin-bottom:15px">
      <el-button type="primary" @click="showAddDialog">新增用户</el-button>
    </div>
    <el-table :data="users" stripe>
      <el-table-column prop="username" label="用户名" width="150" />
      <el-table-column prop="display_name" label="姓名" width="150" />
      <el-table-column prop="role" label="角色" width="100">
        <template #default="{row}"><el-tag :type="row.role==='admin'?'danger':row.role==='config'?'warning':'info'" size="small">{{ row.role }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" width="200" />
      <el-table-column label="操作" width="200">
        <template #default="{row}">
          <el-button size="small" @click="showEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteUser(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit?'编辑用户':'新增用户'" width="400px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名"><el-input v-model="form.username" :disabled="isEdit" /></el-form-item>
        <el-form-item label="密码" v-if="!isEdit"><el-input v-model="form.password" type="password" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role">
            <el-option label="管理员" value="admin" />
            <el-option label="配置用户" value="config" />
            <el-option label="审计用户" value="audit" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">取消</el-button>
        <el-button type="primary" @click="saveUser">{{ isEdit?'保存':'创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { userApi } from '../../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const users = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const form = ref({ username: '', password: '', display_name: '', role: 'user', email: '' })

const loadUsers = async () => {
  try { const r = await userApi.list(); users.value = r.data } catch(e) { console.error(e) }
}
const showAddDialog = () => {
  isEdit.value = false
  form.value = { username: '', password: '', display_name: '', role: 'user', email: '' }
  dialogVisible.value = true
}
const showEditDialog = (row) => {
  isEdit.value = true
  form.value = { ...row, password: '' }
  dialogVisible.value = true
}
const saveUser = async () => {
  try {
    if (isEdit.value) {
      await userApi.update(form.value.id, form.value)
      ElMessage.success('用户已更新')
    } else {
      await userApi.create(form.value)
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await loadUsers()
  } catch(e) { ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message)) }
}
const deleteUser = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除用户 ${row.username}?`)
    await userApi.del(row.id)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch(e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}
onMounted(loadUsers)
</script>
