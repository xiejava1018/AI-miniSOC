import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    redirect: '/dashboard'
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '概览', requiresAuth: true }
  },
  {
    path: '/assets',
    name: 'Assets',
    component: () => import('@/views/Assets.vue'),
    meta: { title: '资产管理', requiresAuth: true }
  },
  {
    path: '/assets/:id',
    name: 'AssetDetail',
    component: () => import('@/views/AssetDetail.vue'),
    meta: { title: '资产详情', requiresAuth: true }
  },
  {
    path: '/incidents',
    name: 'Incidents',
    component: () => import('@/views/Incidents.vue'),
    meta: { title: '事件管理', requiresAuth: true }
  },
  {
    path: '/incidents/:id',
    name: 'IncidentDetail',
    component: () => import('@/views/IncidentDetail.vue'),
    meta: { title: '事件详情', requiresAuth: true }
  },
  {
    path: '/alerts',
    name: 'Alerts',
    component: () => import('@/views/Alerts.vue'),
    meta: { title: '告警管理', requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/system',
    meta: { title: '系统管理', requiresAuth: true },
    children: [
      {
        path: 'users',
        name: 'SystemUsers',
        component: () => import('@/views/system/Users.vue'),
        meta: { title: '用户管理', requiresAuth: true }
      },
      {
        path: 'roles',
        name: 'SystemRoles',
        component: () => import('@/views/system/Roles.vue'),
        meta: { title: '角色管理', requiresAuth: true }
      },
      {
        path: 'menus',
        name: 'SystemMenus',
        component: () => import('@/views/system/Menus.vue'),
        meta: { title: '菜单管理', requiresAuth: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  // 设置页面标题
  document.title = `${to.meta.title || 'AI-miniSOC'} - AI-miniSOC`

  // 检查是否需要认证
  const authStore = useAuthStore()
  const requiresAuth = to.meta.requiresAuth || to.matched.some(record => record.meta.requiresAuth)

  if (requiresAuth && !authStore.isAuthenticated) {
    // 未认证用户访问受保护路由，重定向到登录页
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else {
    // 已认证或公开路由，正常放行
    next()
  }
})

export default router
