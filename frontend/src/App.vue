<template>
  <div id="app">
    <router-view />
    <Toast />
    <GlobalConfirmDialog />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Toast from '@/components/ui/Toast.vue'
import GlobalConfirmDialog from '@/components/GlobalConfirmDialog.vue'
import { useTheme } from '@/composables/useTheme'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const route = useRoute()
const { initTheme } = useTheme()
const authStore = useAuthStore()

// 安全警告标志：远程访问已开启但未设置密码
const showSecurityWarning = ref(false)
provide('showSecurityWarning', showSecurityWarning)

onMounted(async () => {
  initTheme()

  // 初始化认证状态
  await authStore.init()

  if (route.path !== '/') {
    return
  }

  // 远程访问认证检查
  if (!authStore.isLoading) {
    if (!authStore.isAuthenticated && route.path !== '/login' && !route.path.startsWith('/setup/')) {
      // 远程访问且未认证 → 跳转登录
      router.replace('/login')
    }
  }
})
</script>

<style>
#app {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
</style>
