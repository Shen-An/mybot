/**
 * Vue Router 配置 — 多用户支持
 * 使用动态导入实现代码分割，提升首屏加载速度
 */

import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes: RouteRecordRaw[] = [
    {
        path: '/',
        name: 'home',
        component: () => import('../modules/chat/ChatWindow.vue'),
        meta: { requiresAuth: true },
    },
    {
        path: '/login',
        name: 'login',
        component: () => import(/* webpackChunkName: "login" */ '../views/LoginView.vue'),
        meta: { guestOnly: true },
    },
    {
        path: '/setup/:setupSecret',
        name: 'setup',
        component: () => import(/* webpackChunkName: "login" */ '../views/LoginView.vue'),
        meta: { guestOnly: true },
    },
    // 用户管理页面（admin/operator）
    {
        path: '/users',
        name: 'users',
        component: () => import('../modules/settings/UserManagement.vue'),
        meta: { requiresAuth: true, roles: ['admin', 'operator'] },
    },
    // 用户资料页面
    {
        path: '/profile',
        name: 'profile',
        component: () => import('../views/ProfileView.vue'),
        meta: { requiresAuth: true },
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()

    // 如果正在加载，等待加载完成
    if (authStore.isLoading) {
        await authStore.init()
    }

    const requiresAuth = to.meta.requiresAuth === true
    const guestOnly = to.meta.guestOnly === true
    const allowedRoles = to.meta.roles as Array<'admin' | 'operator' | 'user'> | undefined

    // 未认证
    if (!authStore.isAuthenticated) {
        if (requiresAuth) {
            // 需要认证但未登录 → 跳转登录
            next({ name: 'login', query: { redirect: to.fullPath } })
            return
        }
        // guestOnly 页面直接访问
        next()
        return
    }

    // 已认证
    if (guestOnly) {
        // 已登录但访问登录/设置页 → 跳转首页
        next({ name: 'home' })
        return
    }

    // 角色检查
    if (allowedRoles && authStore.user) {
        if (!allowedRoles.includes(authStore.user.role)) {
            // 无权访问 → 跳转首页
            next({ name: 'home' })
            return
        }
    }

    next()
})

export default router
