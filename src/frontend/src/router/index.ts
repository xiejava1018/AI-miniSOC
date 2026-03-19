import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    redirect: '/dashboard'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: {
      title: '登录 - AI-miniSOC',
      requiresAuth: false
    }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: {
      title: '概览仪表板 - AI-miniSOC',
      requiresAuth: true
    }
  },
  {
    path: '/assets',
    name: 'Assets',
    component: () => import('@/views/Assets.vue'),
    meta: {
      title: '资产管理 - AI-miniSOC',
      requiresAuth: true
    }
  },
  {
    path: '/assets/:id',
    name: 'AssetDetail',
    component: () => import('@/views/AssetDetail.vue'),
    meta: {
      title: '资产详情 - AI-miniSOC',
      requiresAuth: true
    }
  },
  {
    path: '/incidents',
    name: 'Incidents',
    component: () => import('@/views/Incidents.vue'),
    meta: {
      title: '事件管理 - AI-miniSOC',
      requiresAuth: true
    }
  },
  {
    path: '/incidents/:id',
    name: 'IncidentDetail',
    component: () => import('@/views/IncidentDetail.vue'),
    meta: {
      title: '事件详情 - AI-miniSOC',
      requiresAuth: true
    }
  },
  {
    path: '/alerts',
    name: 'Alerts',
    component: () => import('@/views/Alerts.vue'),
    meta: {
      title: '告警中心 - AI-miniSOC',
      requiresAuth: true
    }
  },
  // 系统管理路由
  {
    path: '/system',
    redirect: '/system/users',
    meta: { requiresAuth: true }
  },
  {
    path: '/system/users',
    name: 'SystemUsers',
    component: () => import('@/views/system/Users.vue'),
    meta: {
      title: '用户管理 - AI-miniSOC',
      requiresAuth: true,
      permission: 'system-users'
    }
  },
  {
    path: '/system/roles',
    name: 'SystemRoles',
    component: () => import('@/views/system/Roles.vue'),
    meta: {
      title: '角色管理 - AI-miniSOC',
      requiresAuth: true,
      permission: 'system-roles'
    }
  },
  {
    path: '/system/menus',
    name: 'SystemMenus',
    component: () => import('@/views/system/Menus.vue'),
    meta: {
      title: '菜单管理 - AI-miniSOC',
      requiresAuth: true,
      permission: 'system-menus'
    }
  },
  {
    path: '/system/config',
    name: 'SystemConfig',
    component: () => import('@/views/system/Config.vue'),
    meta: {
      title: '系统配置 - AI-miniSOC',
      requiresAuth: true,
      permission: 'system-config'
    }
  },
  {
    path: '/system/audit',
    name: 'SystemAudit',
    component: () => import('@/views/system/AuditLogs.vue'),
    meta: {
      title: '审计日志 - AI-miniSOC',
      requiresAuth: true,
      permission: 'system-audit'
    }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: {
      title: '404 - 页面未找到 - AI-miniSOC'
    }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 全局前置守卫
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 设置页面标题
  if (to.meta.title) {
    document.title = to.meta.title as string
  }

  // 检查路由是否需要认证
  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !authStore.isAuthenticated) {
    // 需要认证但未登录，跳转到登录页
    next('/login')
    return
  }

  // 已登录用户访问登录页，跳转到dashboard
  if (to.path === '/login' && authStore.isAuthenticated) {
    next('/dashboard')
    return
  }

  // 检查权限
  if (to.meta.permission) {
    if (!authStore.hasPermission(to.meta.permission as string)) {
      ElMessage.error('权限不足')
      next('/dashboard')
      return
    }
  }

  next()
})

export default router
