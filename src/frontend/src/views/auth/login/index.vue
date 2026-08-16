<template>
  <div class="login">
    <LoginLeftView></LoginLeftView>

    <div class="right-wrap">
      <div class="top-right-wrap">
        <div v-if="shouldShowThemeToggle" class="btn theme-btn" @click="themeAnimation">
          <i class="iconfont-sys">
            {{ isDark ? '&#xe6b5;' : '&#xe725;' }}
          </i>
        </div>
      </div>
      <div class="header">
        <ArtLogo class="icon" />
        <h1>{{ systemName }}</h1>
      </div>
      <div class="login-wrap">
        <div class="form">
          <h3 class="title">{{ '欢迎回来' }}</h3>
          <p class="sub-title">{{ '输入您的账号和密码登录' }}</p>
          <ElForm
            ref="formRef"
            :model="formData"
            :rules="rules"
            @keyup.enter="handleSubmit"
            style="margin-top: 25px"
          >
            <ElFormItem prop="username">
              <ElInput v-model.trim="formData.username" :placeholder="usernamePlaceholder" />
            </ElFormItem>
            <ElFormItem prop="password">
              <ElInput
                :placeholder="passwordPlaceholder"
                v-model.trim="formData.password"
                type="password"
                radius="8px"
                autocomplete="off"
                show-password
              />
            </ElFormItem>

            <ElFormItem prop="captcha_code" v-if="captchaEnabled">
              <div class="captcha-row">
                <ElInput
                  v-model.trim="formData.captcha_code"
                  placeholder="请输入验证码"
                  style="flex: 1"
                  @keyup.enter="handleSubmit"
                />
                <img
                  v-if="captchaImage"
                  :src="captchaImage"
                  class="captcha-img"
                  @click="refreshCaptcha"
                  title="点击刷新验证码"
                />
              </div>
            </ElFormItem>

            <div class="forget-password">
              <ElCheckbox v-model="formData.rememberPassword">{{ '记住密码' }}</ElCheckbox>
              <RouterLink :to="RoutesAlias.ForgetPassword">{{ '忘记密码' }}</RouterLink>
            </div>

            <div style="margin-top: 30px">
              <ElButton
                class="login-btn"
                type="primary"
                @click="handleSubmit"
                :loading="loading"
                v-ripple
              >
                {{ '登录' }}
              </ElButton>
            </div>
          </ElForm>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRouter, useRoute } from 'vue-router'
  import { storeToRefs } from 'pinia'
  import { RoutesAlias } from '@/router/routesAlias'
  import { ElNotification, ElMessage } from 'element-plus'
  import { useUserStore } from '@/store/modules/user'
  import { useDictStore } from '@/store/modules/dict'
  import { themeAnimation } from '@/utils/theme/animation'
  import { fetchLogin, fetchGetUserInfo, fetchCaptcha } from '@/api/auth'
  import { useHeaderBar } from '@/composables/useHeaderBar'
  import { useSettingStore } from '@/store/modules/setting'
  import { useSystemStore } from '@/store/modules/system'
  import type { FormInstance, FormRules } from 'element-plus'

  defineOptions({ name: 'Login' })

  const settingStore = useSettingStore()
  const { isDark } = storeToRefs(settingStore)
  const { shouldShowThemeToggle } = useHeaderBar()

  const userStore = useUserStore()
  const dictStore = useDictStore()
  const router = useRouter()
  const route = useRoute()
  const systemStore = useSystemStore()

  const systemName = systemStore.appName
  const formRef = ref<FormInstance>()

  const formData = reactive({
    username: '',
    password: '',
    captcha_code: '',
    rememberPassword: true
  })

  const captchaEnabled = ref(true)
  const captchaKey = ref('')
  const captchaImage = ref('')

  const usernamePlaceholder = computed(() => '请输入账号')
  const passwordPlaceholder = computed(() => '请输入密码')

  const rules = computed<FormRules>(() => ({
    username: [{ required: true, message: usernamePlaceholder.value, trigger: 'blur' }],
    password: [{ required: true, message: passwordPlaceholder.value, trigger: 'blur' }],
    captcha_code: captchaEnabled.value
      ? [{ required: true, message: '请输入验证码', trigger: 'blur' }]
      : []
  }))

  const loading = ref(false)

  const refreshCaptcha = async () => {
    try {
      const res = await fetchCaptcha()
      captchaKey.value = res.captcha_key
      captchaImage.value = res.captcha_image
      formData.captcha_code = ''
    } catch (err) {
      console.error('获取验证码失败:', err)
    }
  }

  const handleSubmit = async () => {
    if (!formRef.value) return

    // 防止重复提交
    if (loading.value) return

    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return

    loading.value = true
    try {
      const loginParams: Api.Auth.LoginParams = {
        username: formData.username,
        password: formData.password
      }
      if (captchaEnabled.value && captchaKey.value) {
        loginParams.captcha_key = captchaKey.value
        loginParams.captcha_code = formData.captcha_code
      }

      const loginRes = await fetchLogin(loginParams)

      if (!loginRes.access_token) {
        throw new Error('登录失败，请稍后重试')
      }

      userStore.setToken(loginRes.access_token, loginRes.refresh_token)
      userStore.setLoginStatus(true)

      // 后端登录响应中直接包含用户信息, 尝试使用
      if (loginRes.user) {
        const user = loginRes.user as Api.Auth.UserInfo
        userStore.setUserInfo(user)
      } else {
        // 兼容处理: 如果登录响应中没有用户信息, 再单独获取
        const userInfo = await fetchGetUserInfo().catch((error) => {
          console.error('[Login] fetch user info error:', error)
          return undefined
        })
        if (userInfo) {
          userStore.setUserInfo(userInfo)
        }
      }

      showLoginSuccessNotice()

      // 预加载字典数据
      dictStore.loadAll().catch((e) => console.warn('[Login] 加载字典失败:', e))

      const redirect = route.query.redirect as string | undefined
      // 如果没有重定向参数，跳转到首页
      console.log('[Login] 准备跳转到:', redirect || '/dashboard')
      router.push(redirect || '/dashboard').then(() => {
        console.log('[Login] 跳转成功')
      }).catch((err) => {
        console.error('[Login] 跳转失败:', err)
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : ''
      ElMessage.error(message || '登录失败，请稍后重试')
      // 登录失败后刷新验证码
      if (captchaEnabled.value) {
        await refreshCaptcha()
      }
    } finally {
      loading.value = false
    }
  }

  const showLoginSuccessNotice = () => {
    // 优先用显示名 (full_name), 回退到登录账号 (username)
    const displayName =
      userStore.getUserInfo?.full_name ||
      userStore.getUserInfo?.username ||
      formData.username ||
      ''
    setTimeout(() => {
      ElNotification({
        title: '登录成功',
        type: 'success',
        duration: 2500,
        zIndex: 10000,
        message: displayName ? `欢迎回来, ${displayName}!` : '登录成功'
      })
    }, 150)
  }

  onMounted(() => {
    // 如有重定向参数, 保持用于登录成功后跳转
    if (captchaEnabled.value) {
      refreshCaptcha()
    }
  })
</script>

<style lang="scss" scoped>
  @use './index';

  .captcha-row {
    display: flex;
    align-items: center;
    gap: 10px;

    .captcha-img {
      width: 100px;
      height: 40px;
      cursor: pointer;
      border-radius: 4px;
      border: 1px solid var(--el-border-color);
    }
  }
</style>
