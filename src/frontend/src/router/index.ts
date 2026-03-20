import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

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
    meta: { title: '概览' }
  },
  {
    path: '/assets',
    name: 'Assets',
    component: () => import('@/views/Assets.vue'),
    meta: { title: '资产管理' }
  },
  {
    path: '/assets/:id',
    name: 'AssetDetail',
    component: () => import('@/views/AssetDetail.vue'),
    meta: { title: '资产详情' }
  },
  {
    path: '/incidents',
    name: 'Incidents',
    component: () => import('@/views/Incidents.vue'),
    meta: { title: '事件管理' }
  },
  {
    path: '/incidents/:id',
    name: 'IncidentDetail',
    component: () => import('@/views/IncidentDetail.vue'),
    meta: { title: '事件详情' }
  },
  {
    path: '/alerts',
    name: 'Alerts',
    component: () => import('@/views/Alerts.vue'),
    meta: { title: '告警管理' }
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
  next()
})

export default router
