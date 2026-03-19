<template>
  <div class="not-found-container">
    <div class="not-found-content">
      <div class="error-code">404</div>
      <h1>页面未找到</h1>
      <p class="description">抱歉，您访问的页面不存在。</p>
      <el-button type="primary" @click="goHome">
        返回首页
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const goHome = () => {
  router.push('/dashboard')
}
</script>

<style scoped>
.not-found-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
}

.not-found-content {
  text-align: center;
  padding: 48px;
}

.error-code {
  font-size: 120px;
  font-weight: 700;
  color: var(--accent-cyan);
  line-height: 1;
  margin-bottom: 24px;
  text-shadow: 0 0 40px var(--accent-cyan-dim);
}

.not-found-content h1 {
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px 0;
}

.description {
  font-size: 16px;
  color: var(--text-muted);
  margin-bottom: 32px;
}
</style>
