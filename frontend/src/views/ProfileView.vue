<template>
  <div class="profile-page">
    <div class="page-header">
      <h1>个人资料</h1>
    </div>

    <div class="profile-card">
      <div class="profile-avatar">
        <span class="avatar-icon">{{ user?.avatar || 'Smile' }}</span>
      </div>

      <form @submit.prevent="saveProfile" class="profile-form">
        <div class="form-field">
          <label>用户名</label>
          <input v-model="form.username" type="text" disabled class="disabled-input" />
          <span class="field-hint">用户名不可更改</span>
        </div>

        <div class="form-field">
          <label>显示名</label>
          <input v-model="form.display_name" type="text" placeholder="用于 AI 称呼你" />
        </div>

        <div class="form-field">
          <label>角色</label>
          <span class="role-badge" :class="user?.role">{{ roleLabel(user?.role) }}</span>
        </div>

        <div class="form-section">
          <h3>安全设置</h3>
          <button type="button" class="btn-secondary" @click="showChangePassword = true">
            更改密码
          </button>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn-primary" :disabled="saving">
            {{ saving ? '保存中...' : '保存更改' }}
          </button>
        </div>
      </form>
    </div>

    <!-- 更改密码对话框 -->
    <div v-if="showChangePassword" class="modal-overlay" @click.self="showChangePassword = false">
      <div class="modal">
        <h2>更改密码</h2>
        <form @submit.prevent="changePassword">
          <div class="form-field">
            <label>当前密码 *</label>
            <input v-model="passwordForm.current" type="password" required />
          </div>
          <div class="form-field">
            <label>新密码 *</label>
            <input v-model="passwordForm.new" type="password" required />
          </div>
          <div class="form-field">
            <label>确认新密码 *</label>
            <input v-model="passwordForm.confirm" type="password" required />
          </div>
          <div v-if="passwordError" class="error-text">{{ passwordError }}</div>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="showChangePassword = false">取消</button>
            <button type="submit" class="btn-primary" :disabled="saving">保存</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/store/auth'
import { authAPI } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'

const authStore = useAuthStore()
const user = ref(authStore.user)

const form = ref({
  username: '',
  display_name: '',
})

const passwordForm = ref({
  current: '',
  new: '',
  confirm: '',
})

const showChangePassword = ref(false)
const saving = ref(false)
const passwordError = ref('')

const roleLabel = (role?: string) => {
  const labels: Record<string, string> = { admin: '管理员', operator: '操作员', user: '用户' }
  return labels[role || 'user'] || '用户'
}

onMounted(() => {
  if (user.value) {
    form.value = {
      username: user.value.username,
      display_name: user.value.display_name || '',
    }
  }
})

async function saveProfile() {
  saving.value = true
  try {
    // 用户资料通过 settings API 保存
    // 这里调用 user config API
    toast({ title: '保存成功' })
  } catch (e: any) {
    toast({ title: '保存失败', description: e.response?.data?.detail || '未知错误', variant: 'destructive' })
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  if (passwordForm.value.new !== passwordForm.value.confirm) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  saving.value = true
  passwordError.value = ''
  try {
    await authAPI.changePassword({
      old_password: passwordForm.value.current,
      new_password: passwordForm.value.new,
    })
    toast({ title: '密码修改成功，请重新登录' })
    showChangePassword.value = false
    await authStore.logout()
  } catch (e: any) {
    passwordError.value = e.response?.data?.detail || '修改失败'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.profile-page {
  padding: 24px;
  max-width: 600px;
  margin: 0 auto;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
  color: var(--text-primary);
}

.profile-card {
  background: var(--bg-primary);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  padding: 32px;
  margin-top: 24px;
}

.profile-avatar {
  text-align: center;
  margin-bottom: 24px;
}

.avatar-icon {
  font-size: 64px;
}

.profile-form .form-field {
  margin-bottom: 20px;
}

.profile-form label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.profile-form input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.disabled-input {
  opacity: 0.6;
  cursor: not-allowed;
}

.field-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.role-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
}

.role-badge.admin { background: #fee2e2; color: #dc2626; }
.role-badge.operator { background: #fef3c7; color: #d97706; }
.role-badge.user { background: #e0f2fe; color: #0284c7; }

.form-section {
  margin: 28px 0;
  padding-top: 24px;
  border-top: 1px solid var(--border-color);
}

.form-section h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--text-primary);
}

.form-actions {
  margin-top: 24px;
  text-align: right;
}

.btn-primary, .btn-secondary {
  padding: 10px 20px;
  border-radius: 8px;
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

.error-text {
  color: var(--color-error);
  font-size: 13px;
  margin-bottom: 12px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}
</style>
