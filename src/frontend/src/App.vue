<template>
  <el-container class="app-container">
    <el-aside width="200px" class="sidebar">
      <div class="logo">
        <h2>AI-miniSOC</h2>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#001529"
        text-color="#fff"
        active-text-color="#1890ff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>概览</span>
        </el-menu-item>
        <el-menu-item index="/assets">
          <el-icon><Monitor /></el-icon>
          <span>资产管理</span>
        </el-menu-item>
        <el-menu-item index="/incidents">
          <el-icon><Warning /></el-icon>
          <span>事件管理</span>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <el-icon><Bell /></el-icon>
          <span>告警管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">AI驱动的微型安全运营中心</div>
        <div class="header-user">
          <el-dropdown>
            <span class="el-dropdown-link">
              <el-icon><User /></el-icon>
              管理员
            </span>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { HomeFilled, Monitor, Warning, Bell, User } from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background-color: #001529;
  height: 100vh;
}

.logo {
  padding: 20px;
  text-align: center;
  color: #fff;
  border-bottom: 1px solid #1f2937;
}

.logo h2 {
  margin: 0;
  font-size: 20px;
}

.header {
  background-color: #fff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.header-title {
  font-size: 18px;
  font-weight: 500;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.el-dropdown-link {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}

.main-content {
  background-color: #f3f4f6;
  padding: 0;
}
</style>
