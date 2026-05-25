/**
 * Auth Pinia Store — 多用户认证状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authAPI } from '@/api/auth'

export interface UserInfo {
  user_id: number
  username: string
  role: 'admin' | 'operator' | 'user'
  display_name?: string
  avatar?: string
  is_active: boolean
  created_at?: string
  last_login_at?: string
}

export interface AuthState {
  isAuthenticated: boolean
  user: UserInfo | null
  token: string | null
  isLoading: boolean
  impersonating: boolean // 是否处于切换用户状态
  originalUser: UserInfo | null // 切换用户时保存原管理员信息
}

export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref(false)
  const user = ref<UserInfo | null>(null)
  const token = ref<string | null>(null)
  const isLoading = ref(true)
  const impersonating = ref(false)
  const originalUser = ref<UserInfo | null>(null)

  const isAdmin = computed(() => user.value?.role === 'admin')
  const isOperator = computed(() => user.value?.role === 'operator')
  const isUserRole = computed(() => user.value?.role === 'user')

  /**
   * 初始化认证状态（应用启动时调用）
   */
  async function init() {
    isLoading.value = true
    try {
      const status = await authAPI.status()
      if (status.authenticated && status.user_id) {
        isAuthenticated.value = true
        user.value = {
          user_id: status.user_id,
          username: status.username,
          role: status.role,
          display_name: status.display_name,
          avatar: status.avatar,
          is_active: true,
        }
        token.value = localStorage.getItem('CountBot_token')
      } else {
        isAuthenticated.value = false
        user.value = null
        token.value = null
      }
    } catch (e) {
      isAuthenticated.value = false
      user.value = null
      token.value = null
    } finally {
      isLoading.value = false
    }
  }

  /**
   * 登录
   */
  async function login(username: string, password: string) {
    const response = await authAPI.login({ username, password })
    if (response.success && response.token) {
      token.value = response.token
      localStorage.setItem('CountBot_token', response.token)
      isAuthenticated.value = true
      user.value = {
        user_id: response.user_id,
        username: response.username,
        role: response.role,
        display_name: response.display_name,
        is_active: true,
      }
      return true
    }
    return false
  }

  /**
   * 首次设置（创建第一个管理员）
   */
  async function setup(username: string, password: string, setupSecret?: string) {
    const response = await authAPI.setup({ username, password }, setupSecret)
    if (response.success && response.token) {
      token.value = response.token
      localStorage.setItem('CountBot_token', response.token)
      isAuthenticated.value = true
      user.value = {
        user_id: response.user_id,
        username: response.username,
        role: 'admin',
        display_name: response.display_name,
        is_active: true,
      }
      return true
    }
    return false
  }

  /**
   * 注销
   */
  async function logout() {
    if (token.value) {
      try {
        await authAPI.logout()
      } catch (e) {
        // 忽略注销请求失败
      }
    }
    // 清除切换用户状态
    if (impersonating.value && originalUser.value) {
      // 退出切换
      try {
        await authAPI.switchDelete()
      } catch (e) {
        // 忽略
      }
    }
    token.value = null
    localStorage.removeItem('CountBot_token')
    isAuthenticated.value = false
    user.value = null
    impersonating.value = false
    originalUser.value = null
  }

  /**
   * 刷新当前用户信息
   */
  async function fetchUser() {
    try {
      const me = await authAPI.me()
      if (me.user_id) {
        user.value = {
          user_id: me.user_id,
          username: me.username,
          role: me.role,
          display_name: me.display_name,
          avatar: me.avatar,
          is_active: me.is_active,
          created_at: me.created_at,
          last_login_at: me.last_login_at,
        }
        isAuthenticated.value = true
      }
    } catch (e) {
      // 用户未登录或 token 无效
      isAuthenticated.value = false
      user.value = null
    }
  }

  /**
   * 管理员切换用户（sudo 模式）
   */
  async function switchUser(targetUserId: number) {
    const response = await authAPI.switchPost(targetUserId)
    if (response.success && response.switch_token) {
      // 保存原用户信息
      originalUser.value = { ...user.value! }
      // 更新当前用户
      user.value = {
        user_id: response.target_user_id,
        username: response.target_username,
        role: response.target_role,
        is_active: true,
      }
      impersonating.value = true
      // 存储切换 token
      localStorage.setItem('CountBot_switch_token', response.switch_token)
      return true
    }
    return false
  }

  /**
   * 退出切换，返回管理员身份
   */
  async function exitImpersonation() {
    try {
      await authAPI.switchDelete()
    } catch (e) {
      // 忽略
    }
    localStorage.removeItem('CountBot_switch_token')
    impersonating.value = false
    // 恢复原管理员信息
    if (originalUser.value) {
      user.value = { ...originalUser.value }
      originalUser.value = null
    }
  }

  /**
   * 清除所有认证数据（用于强制登出）
   */
  function clear() {
    token.value = null
    localStorage.removeItem('CountBot_token')
    localStorage.removeItem('CountBot_switch_token')
    isAuthenticated.value = false
    user.value = null
    impersonating.value = false
    originalUser.value = null
  }

  return {
    // State
    isAuthenticated,
    user,
    token,
    isLoading,
    impersonating,
    originalUser,
    // Computed
    isAdmin,
    isOperator,
    isUserRole,
    // Actions
    init,
    login,
    setup,
    logout,
    fetchUser,
    switchUser,
    exitImpersonation,
    clear,
  }
})
