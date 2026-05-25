<template>
  <div class="user-switcher" v-if="authStore.isAdmin && authStore.user">
    <div class="user-menu" @click="menuOpen = !menuOpen">
      <span class="user-avatar">{{ authStore.user.avatar || '👤' }}</span>
      <span class="user-name">{{ authStore.user.display_name || authStore.user.username }}</span>
      <span class="role-badge" :class="authStore.user.role">{{ roleLabel(authStore.user.role) }}</span>
      <svg class="chevron" viewBox="0 0 24 24" width="16" height="16">
        <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2"/>
      </svg>
    </div>

    <div v-if="menuOpen" class="user-menu-dropdown" @click.outside="menuOpen = false">
      <div class="menu-header">
        <span class="current-user">{{ authStore.user.username }}</span>
        <span v-if="authStore.impersonating" class="impersonating-tag">
          以 {{ authStore.originalUser?.username }} 身份
        </span>
      </div>

      <div class="menu-section">
        <div class="menu-item" @click="router.push('/profile')">
          <svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 12c2.5 0 4.5-2 4.5-4.5S14.5 3 12 3 7.5 5 7.5 7.5 9.5 12 12 12z"/><path d="M5 20c0-3 3-5 7-5s7 2 7 5"/></svg>
          个人资料
        </div>
        <div v-if="authStore.isAdmin" class="menu-item" @click="router.push('/users')">
          <svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-2.7 0-8 1.3-8 4v2h16v-2c0-2.7-5.3-4-8-4z"/><path d="M4 10v8c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-8H4zm4 3v2H6v-2h2zm4 0v2h-2v-2h2zm4 0v2h-2v-2h2z"/></svg>
          用户管理
        </div>
      </div>

      <div class="menu-section" v-if="authStore.impersonating">
        <div class="menu-item danger" @click="exitImpersonation">
          <svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 3v9m0 0l-3-3m3 3l3-3M5 20h14"/></svg>
          返回管理员
        </div>
      </div>

      <div class="menu-section">
        <div class="menu-item" @click="handleLogout">
          <svg viewBox="0 0 24 24" width="18" height="18"><path d="M10 3H6c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h4v-2H6V5h4V3zm8 5l-1.4-1.4L17.2 7H11v2h6.2l-2.6 2.4L18 12.8 22 8.8z"/></svg>
          注销
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()
const menuOpen = ref(false)

const roleLabel = (role: string) => {
  const labels: Record<string, string> = { admin: '管理员', operator: '操作员', user: '用户' }
  return labels[role] || role
}

async function exitImpersonation() {
  await authStore.exitImpersonation()
  menuOpen.value = false
}

async function handleLogout() {
  if (confirm('确定要注销吗？')) {
    await authStore.logout()
    router.replace('/login')
  }
}
</script>

<style scoped>
.user-switcher {
  position: relative;
}

.user-menu {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.user-menu:hover {
  background: var(--bg-secondary);
}

.user-avatar {
  font-size: 20px;
}

.user-name {
  font-size: 14px;
  color: var(--text-primary);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
}

.role-badge.admin { background: #fee2e2; color: #dc2626; }
.role-badge.operator { background: #fef3c7; color: #d97706; }
.role-badge.user { background: #e0f2fe; color: #0284c7; }

.chevron {
  transition: transform 0.2s;
}

.user-menu[aria-expanded="true"] .chevron {
  transform: rotate(180deg);
}

.user-menu-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  min-width: 220px;
  z-index: 1000;
  overflow: hidden;
}

.menu-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.current-user {
  display: block;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
}

.impersonating-tag {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-warning);
}

.menu-section {
  padding: 8px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary);
  transition: background 0.15s;
}

.menu-item:hover {
  background: var(--bg-secondary);
}

.menu-item.danger {
  color: var(--color-error);
}

.menu-item.danger:hover {
  background: #fee2e2;
}
</style>
