<template>
  <div class="page-container">
    <div class="page-header">
      <h1>系统配置</h1>
      <p class="page-subtitle">系统参数和配置管理功能</p>
    </div>

    <el-card class="coming-soon-card">
      <div class="coming-soon-content">
        <el-icon :size="64" color="var(--accent-cyan)">
          <Lock />
        </el-icon>
        <h2>功能开发中</h2>
        <p>系统配置功能正在开发中，敬请期待...</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { Lock } from '@element-plus/icons-vue'
</script>

<style scoped>
.page-container {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.coming-soon-card {
  max-width: 600px;
  margin: 48px auto;
}

.coming-soon-content {
  text-align: center;
  padding: 48px 24px;
}

.coming-soon-content h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 24px 0 12px 0;
}

.coming-soon-content p {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}
</style>
