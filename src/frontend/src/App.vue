<template>
  <div class="soc-container">
    <!-- Animated Background -->
    <div class="bg-gradient"></div>
    <div class="bg-grid"></div>

    <!-- Sidebar -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <div class="logo-container">
          <div class="logo-icon">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="logo-text" v-show="!sidebarCollapsed">
            <h1>AI-miniSOC</h1>
            <span class="logo-tagline">智能安全运营中心</span>
          </div>
        </div>
        <button class="collapse-btn" @click="toggleSidebar" :title="sidebarCollapsed ? '展开菜单' : '收起菜单'">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <nav class="sidebar-nav">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          :title="sidebarCollapsed ? item.label : ''"
        >
          <component :is="item.icon" class="nav-icon" />
          <span class="nav-label" v-show="!sidebarCollapsed">{{ item.label }}</span>
          <div class="nav-indicator"></div>
        </router-link>
      </nav>

      <div class="sidebar-footer" v-show="!sidebarCollapsed">
        <div class="status-indicator">
          <div class="status-dot pulse-animation"></div>
          <span>系统在线</span>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <div class="main-wrapper">
      <!-- Header -->
      <header class="header">
        <div class="header-left">
          <h2 class="page-title">{{ currentPageTitle }}</h2>
          <div class="breadcrumb">
            <span>AI-miniSOC</span>
            <svg class="breadcrumb-separator" viewBox="0 0 24 24" fill="none">
              <path d="M9 18L15 12L9 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>{{ currentPageTitle }}</span>
          </div>
        </div>

        <div class="header-right">
          <div class="header-stats">
            <div class="stat-badge">
              <svg viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                <path d="M12 6V12L16 14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
              <span>{{ currentTime }}</span>
            </div>
          </div>

          <div class="header-actions">
            <button class="icon-btn" :title="themeStore.theme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'" @click="themeStore.toggleTheme">
              <svg v-if="themeStore.theme === 'dark'" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="2"/>
                <path d="M12 1V3M12 21V23M4.22 4.22L5.64 5.64M18.36 18.36L19.78 19.78M1 12H3M21 12H23M4.22 19.78L5.64 18.36M18.36 5.64L19.78 4.22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
            <button class="icon-btn" title="通知">
              <el-icon><Bell /></el-icon>
              <span class="badge">3</span>
            </button>
            <div class="user-profile">
              <div class="user-avatar">
                <svg viewBox="0 0 24 24" fill="none">
                  <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  <circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/>
                </svg>
              </div>
              <span class="user-name">管理员</span>
            </div>
          </div>
        </div>
      </header>

      <!-- Content Area -->
      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, markRaw } from 'vue'
import { useRoute } from 'vue-router'
import { HomeFilled, Monitor, Warning, Bell, User, DataAnalysis } from '@element-plus/icons-vue'
import { useThemeStore } from '@/stores/theme'

const route = useRoute()
const themeStore = useThemeStore()

// Sidebar collapse state
const sidebarCollapsed = ref(false)

// Load sidebar state from localStorage
const savedSidebarState = localStorage.getItem('sidebarCollapsed')
if (savedSidebarState !== null) {
  sidebarCollapsed.value = savedSidebarState === 'true'
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('sidebarCollapsed', String(sidebarCollapsed.value))
}

interface MenuItem {
  path: string
  label: string
  icon: any
}

const menuItems: MenuItem[] = [
  { path: '/dashboard', label: '概览仪表板', icon: markRaw(DataAnalysis) },
  { path: '/assets', label: '资产管理', icon: markRaw(Monitor) },
  { path: '/incidents', label: '事件管理', icon: markRaw(Warning) },
  { path: '/alerts', label: '告警中心', icon: markRaw(Bell) },
]

const currentTime = ref('')
let timeInterval: ReturnType<typeof setInterval> | null = null

const currentPageTitle = computed(() => {
  const item = menuItems.find(item => item.path === route.path)
  return item?.label || 'AI-miniSOC'
})

const isActive = (path: string) => {
  return route.path === path
}

const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

onMounted(() => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)
})

onUnmounted(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
})
</script>

<style scoped>
.soc-container {
  display: flex;
  height: 100vh;
  position: relative;
  overflow: hidden;
}

/* Background Effects */
.bg-gradient {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background:
    var(--bg-gradient-1),
    var(--bg-gradient-2),
    var(--bg-primary);
  z-index: -2;
  transition: background var(--transition-base);
}

.bg-grid {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    linear-gradient(rgba(75, 85, 99, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(75, 85, 99, 0.1) 1px, transparent 1px);
  background-size: 50px 50px;
  z-index: -1;
  mask-image: radial-gradient(ellipse at center, black 40%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 40%, transparent 80%);
  transition: background-image var(--transition-base);
}

[data-theme="light"] .bg-grid {
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.15) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.15) 1px, transparent 1px);
}

/* Sidebar */
.sidebar {
  width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 10;
  transition: width var(--transition-base);
}

.sidebar.collapsed {
  width: 72px;
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: padding var(--transition-base);
}

.sidebar.collapsed .sidebar-header {
  padding: 24px 12px;
  justify-content: center;
}

.logo-container {
  display: flex;
  align-items: center;
  gap: 12px;
  transition: gap var(--transition-base);
}

.sidebar.collapsed .logo-container {
  gap: 0;
}

.logo-icon {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 4px 12px var(--accent-cyan-dim);
}

.logo-icon svg {
  width: 24px;
  height: 24px;
}

.logo-text h1 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  margin: 0;
  line-height: 1.2;
}

.logo-tagline {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  transition: opacity var(--transition-base);
}

.sidebar.collapsed .logo-tagline {
  opacity: 0;
  width: 0;
}

/* Collapse Button */
.collapse-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.collapse-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.08);
}

.collapse-btn svg {
  width: 16px;
  height: 16px;
  transition: transform var(--transition-base);
}

.sidebar.collapsed .collapse-btn svg {
  transform: rotate(180deg);
}

/* Navigation */
.sidebar-nav {
  flex: 1;
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sidebar.collapsed .sidebar-nav {
  padding: 20px 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  color: var(--text-secondary);
  text-decoration: none;
  position: relative;
  transition: all var(--transition-base);
  overflow: hidden;
  white-space: nowrap;
}

.sidebar.collapsed .nav-item {
  padding: 12px;
  justify-content: center;
}

.nav-item::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--accent-cyan-dim), transparent);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.nav-item:hover {
  color: var(--text-primary);
  background: rgba(0, 212, 255, 0.08);
}

.nav-item:hover::before {
  opacity: 1;
}

.nav-item.active {
  color: var(--accent-cyan);
  background: linear-gradient(135deg, var(--accent-cyan-dim), rgba(0, 212, 255, 0.05));
}

.nav-item.active::after {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 60%;
  background: var(--accent-cyan);
  border-radius: 0 2px 2px 0;
  box-shadow: 0 0 8px var(--accent-cyan);
}

.sidebar.collapsed .nav-item.active::after {
  width: 3px;
}

.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.nav-label {
  font-size: 14px;
  font-weight: 500;
  position: relative;
  z-index: 1;
  transition: opacity var(--transition-base);
}

.sidebar.collapsed .nav-label {
  opacity: 0;
  width: 0;
}

/* Sidebar Footer */
.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color);
  transition: padding var(--transition-base);
}

.sidebar.collapsed .sidebar-footer {
  padding: 16px 8px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: opacity var(--transition-base);
}

.sidebar.collapsed .status-indicator {
  opacity: 0;
  width: 0;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: var(--status-success);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--status-success);
}

/* Main Content */
.main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.header {
  height: 72px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.breadcrumb-separator {
  width: 14px;
  height: 14px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.header-stats {
  display: flex;
  gap: 16px;
}

.stat-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.stat-badge svg {
  width: 16px;
  height: 16px;
  color: var(--accent-cyan);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.icon-btn {
  position: relative;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.icon-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.08);
}

.icon-btn .badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--status-critical);
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px 6px 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.user-profile:hover {
  border-color: var(--accent-cyan);
}

.user-avatar {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.user-avatar svg {
  width: 18px;
  height: 18px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

/* Content */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 32px;
}

/* Page Transition */
.page-enter-active,
.page-leave-active {
  transition: all var(--transition-base);
}

.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
