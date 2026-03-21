import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  // 从localStorage初始化
  const savedToken = localStorage.getItem('token')
  const savedUser = localStorage.getItem('user')

  const user = ref<any>(savedUser ? JSON.parse(savedUser) : null)
  const token = ref<string | null>(savedToken)

  // 验证token是否过期
  const isAuthenticated = computed(() => {
    if (!token.value) return false

    try {
      // 解析JWT token检查过期时间
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      const exp = payload.exp
      if (exp && exp < Date.now() / 1000) {
        // Token已过期
        clearAuth()
        return false
      }
      return true
    } catch (e) {
      // Token无效
      clearAuth()
      return false
    }
  })

  const isAdmin = computed(() => user.value?.is_admin || false)

  function setAuth(authToken: string, userData: any) {
    token.value = authToken
    user.value = userData
    // 持久化到localStorage
    localStorage.setItem('token', authToken)
    localStorage.setItem('user', JSON.stringify(userData))
  }

  function clearAuth() {
    token.value = null
    user.value = null
    // 从localStorage删除
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    localStorage.removeItem('refresh_token')
  }

  return {
    user,
    token,
    isAuthenticated,
    isAdmin,
    setAuth,
    clearAuth
  }
})
