<template>
  <div class="login-container">
    <!-- Background effects -->
    <div class="bg-gradient"></div>
    <div class="bg-grid"></div>

    <!-- Login card -->
    <div class="login-card glass-effect stagger-in">
      <!-- Logo -->
      <div class="login-logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h1 class="logo-title">AI-miniSOC</h1>
        <p class="logo-subtitle">智能安全运营中心</p>
      </div>

      <!-- Login form -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <!-- Username -->
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <!-- Password -->
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <!-- Remember me -->
        <el-form-item>
          <el-checkbox v-model="form.rememberMe">记住我</el-checkbox>
        </el-form-item>

        <!-- Login button -->
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
            class="login-button"
          >
            {{ loading ? '登录中...' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- Footer links -->
      <div class="login-footer">
        <a href="#" class="forgot-password">忘记密码？</a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

// Form reference
const formRef = ref<FormInstance>()

// Loading state
const loading = ref(false)

// Form data
const form = reactive({
  username: '',
  password: '',
  rememberMe: false
})

// Form validation rules
const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为3-50个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度为6-100个字符', trigger: 'blur' }
  ]
}

// Login handler
const handleLogin = async () => {
  if (!formRef.value) return

  try {
    // Validate form
    await formRef.value.validate()

    loading.value = true

    // Call login
    const result = await authStore.login(form.username, form.password)

    if (result.success) {
      ElMessage.success('登录成功')
      // Redirect to dashboard
      router.push('/dashboard')
    } else {
      ElMessage.error(result.error || '登录失败')
    }
  } catch (error) {
    console.error('Login error:', error)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

/* Background effects */
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

/* Login card */
.login-card {
  width: 100%;
  max-width: 420px;
  padding: 48px;
  border-radius: 16px;
  box-shadow: var(--shadow-lg);
  animation: fadeInUp 0.5s ease;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Logo */
.login-logo {
  text-align: center;
  margin-bottom: 40px;
}

.logo-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 8px 24px var(--accent-cyan-dim);
}

.logo-icon svg {
  width: 32px;
  height: 32px;
}

.logo-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px 0;
  letter-spacing: -0.5px;
}

.logo-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* Form */
.login-form {
  margin-top: 32px;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 24px;
}

.login-form :deep(.el-input__wrapper) {
  padding: 12px 16px;
  border-radius: 8px;
}

.login-form :deep(.el-checkbox__label) {
  color: var(--text-secondary);
  font-size: 14px;
}

/* Login button */
.login-button {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 8px;
  margin-top: 8px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
  border: none;
  transition: all var(--transition-base);
}

.login-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--accent-cyan-dim);
}

.login-button:active {
  transform: translateY(0);
}

/* Footer */
.login-footer {
  text-align: center;
  margin-top: 24px;
}

.forgot-password {
  color: var(--text-muted);
  font-size: 14px;
  text-decoration: none;
  transition: color var(--transition-fast);
}

.forgot-password:hover {
  color: var(--accent-cyan);
}

/* Responsive */
@media (max-width: 768px) {
  .login-card {
    max-width: 90%;
    padding: 32px 24px;
  }

  .logo-title {
    font-size: 24px;
  }

  .logo-subtitle {
    font-size: 12px;
  }
}
</style>
