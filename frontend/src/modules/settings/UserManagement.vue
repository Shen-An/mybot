<template>
  <div class="user-management">
    <div class="page-header">
      <h1>用户管理</h1>
      <button class="btn-primary" @click="showCreateDialog = true">+ 添加用户</button>
    </div>

    <div class="user-table">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>显示名</th>
            <th>角色</th>
            <th>状态</th>
            <th>最后登录</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.id }}</td>
            <td>{{ u.username }}</td>
            <td>{{ u.display_name || '-' }}</td>
            <td>
              <span class="role-badge" :class="u.role">
                {{ roleLabel(u.role) }}
              </span>
            </td>
            <td>
              <span :class="['status-dot', u.is_active ? 'active' : 'inactive']" />
              {{ u.is_active ? '激活' : '禁用' }}
            </td>
            <td>{{ u.last_login_at ? formatTime(u.last_login_at) : '从未' }}</td>
            <td>
              <button class="btn-text" @click="editUser(u)">编辑</button>
              <button
                v-if="u.id !== authStore.user?.id"
                class="btn-text text-danger"
                @click="deleteUser(u.id)"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 创建/编辑用户对话框 -->
    <div v-if="showCreateDialog || editingUser" class="modal-overlay" @click.self="closeDialog">
      <div class="modal">
        <h2>{{ editingUser ? '编辑用户' : '添加用户' }}</h2>
        <form @submit.prevent="saveUser">
          <div class="form-field">
            <label>用户名 *</label>
            <input v-model="form.username" type="text" required :disabled="!!editingUser" />
          </div>
          <div class="form-field" v-if="!editingUser">
            <label>密码 *</label>
            <input v-model="form.password" type="password" required />
          </div>
          <div class="form-field">
            <label>显示名</label>
            <input v-model="form.display_name" type="text" />
          </div>
          <div class="form-field">
            <label>角色 *</label>
            <select v-model="form.role" required>
              <option value="user">用户</option>
              <option value="operator">操作员</option>
              <option value="admin" v-if="authStore.isAdmin">管理员</option>
            </select>
          </div>
          <div class="form-field" v-if="authStore.isAdmin || editingUser?.role !== 'admin'">
            <label>
              <input type="checkbox" v-model="form.is_active" /> 激活
            </label>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="closeDialog">取消</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '@/store/auth'
import { authAPI } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'
const toast = useToast()

const authStore = useAuthStore()

const users = ref<Array<{
  id: number
  username: string
  role: string
  display_name?: string
  avatar?: string
  is_active: boolean
  created_at?: string
  last_login_at?: string
}>>([])

const showCreateDialog = ref(false)
const editingUser = ref<typeof users.value[0] | null>(null)
const saving = ref(false)

const form = ref({
  username: '',
  password: '',
  display_name: '',
  role: 'user' as 'user' | 'operator' | 'admin',
  is_active: true,
})

const roleLabel = (role: string) => {
  const labels: Record<string, string> = { admin: '管理员', operator: '操作员', user: '用户' }
  return labels[role] || role
}

const formatTime = (iso: string) => {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN')
}

async function loadUsers() {
  try {
    users.value = await authAPI.listUsers()
  } catch (e: any) {
    toast({ title: '加载失败', description: e.response?.data?.detail || '未知错误', variant: 'destructive' })
  }
}

function editUser(user: typeof users.value[0]) {
  editingUser.value = user
  form.value = {
    username: user.username,
    password: '',
    display_name: user.display_name || '',
    role: user.role,
    is_active: user.is_active,
  }
}

function closeDialog() {
  showCreateDialog.value = false
  editingUser.value = null
  form.value = { username: '', password: '', display_name: '', role: 'user', is_active: true }
}

async function saveUser() {
  saving.value = true
  try {
    if (editingUser.value) {
      await authAPI.updateUser(editingUser.value.id, {
        username: form.value.username || undefined,
        display_name: form.value.display_name || undefined,
        role: form.value.role !== editingUser.value.role ? form.value.role : undefined,
        is_active: form.value.is_active !== editingUser.value.is_active ? form.value.is_active : undefined,
      })
      toast({ title: '更新成功' })
    } else {
      await authAPI.createUser({
        username: form.value.username,
        password: form.value.password,
        display_name: form.value.display_name || undefined,
        role: form.value.role,
      })
      toast({ title: '创建成功' })
    }
    closeDialog()
    await loadUsers()
  } catch (e: any) {
    toast({ title: '操作失败', description: e.response?.data?.detail || '未知错误', variant: 'destructive' })
  } finally {
    saving.value = false
  }
}

async function deleteUser(id: number) {
  if (!confirm('确定要删除此用户吗？此操作不可恢复。')) return
  try {
    await authAPI.deleteUser(id)
    toast({ title: '删除成功' })
    await loadUsers()
  } catch (e: any) {
    toast({ title: '删除失败', description: e.response?.data?.detail || '未知错误', variant: 'destructive' })
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.user-management {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
  color: var(--text-primary);
}

.user-table {
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  overflow: hidden;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

th {
  background: var(--bg-secondary);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 13px;
}

td {
  color: var(--text-primary);
  font-size: 14px;
}

.role-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.role-badge.admin { background: #fee2e2; color: #dc2626; }
.role-badge.operator { background: #fef3c7; color: #d97706; }
.role-badge.user { background: #e0f2fe; color: #0284c7; }

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.status-dot.active { background: #22c55e; }
.status-dot.inactive { background: #94a3b8; }

.btn-text {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 0;
}

.btn-text:hover { text-decoration: underline; }
.btn-text.text-danger { color: var(--color-error); }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-width: 90vw;
}

.modal h2 {
  margin: 0 0 20px;
  font-size: 20px;
  color: var(--text-primary);
}

.form-field {
  margin-bottom: 16px;
}

.form-field label {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
  color: var(--text-secondary);
}

.form-field input, .form-field select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.form-field input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.btn-primary, .btn-secondary {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}
</style>
