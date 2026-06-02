/**
 * 系统全局信息 store
 *
 * 从后端 /api/v1/public/system-info 拉取应用名称 / Logo / 版权 / 描述，
 * 给顶栏 / 登录页 / 浏览器 title / 关于弹窗 等使用。
 *
 * ## 加载时机
 * main.ts 在 app.mount() 之前同步 await fetchSystemInfo()，
 * 保证首屏渲染时名称已就位（避免登录页闪现旧名）。
 *
 * ## 兜底
 * 接口失败 / 字段缺失时使用 FALLBACK 默认值，
 * UI 不会出现空白。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getPublicSystemInfo } from '@/api/public'

/** 兜底值：接口失败时使用，确保 UI 不空白 */
const FALLBACK = {
  system_name: 'AI-miniSOC',
  system_logo: '',
  system_copyright: '© 2026 AI-miniSOC',
  system_description: 'AI-driven mini Security Operation Center',
} as const

export const useSystemStore = defineStore('systemStore', () => {
  /** 应用名称（浏览器 title / 顶栏 / 登录页 / 关于） */
  const appName = ref<string>(FALLBACK.system_name)
  /** Logo URL（顶栏 logo 区域，预留字段） */
  const logo = ref<string>(FALLBACK.system_logo)
  /** 版权信息（页脚 / 关于弹窗） */
  const copyright = ref<string>(FALLBACK.system_copyright)
  /** 描述（关于弹窗） */
  const description = ref<string>(FALLBACK.system_description)
  /** 是否已成功拉取过一次 */
  const loaded = ref(false)

  /**
   * 拉取系统信息（应用启动时调一次即可）
   * - 接口失败 / 字段缺失：保留兜底
   * - 不抛异常：登录前 UI 不能因为这个挂掉
   */
  async function fetchSystemInfo(): Promise<void> {
    try {
      const data = await getPublicSystemInfo()
      if (data) {
        if (data.system_name) appName.value = data.system_name
        if (data.system_logo !== undefined) logo.value = data.system_logo
        if (data.system_copyright) copyright.value = data.system_copyright
        if (data.system_description) description.value = data.system_description
        loaded.value = true
      }
    } catch (e) {
      // 静默失败：保留兜底值
      // eslint-disable-next-line no-console
      console.warn('[systemStore] fetchSystemInfo failed, using fallback', e)
    }
  }

  return {
    appName,
    logo,
    copyright,
    description,
    loaded,
    fetchSystemInfo,
  }
})
