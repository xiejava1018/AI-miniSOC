import App from './App.vue'
import { createApp } from 'vue'
import { initStore } from './store'                 // Store
import { initRouter } from './router'               // Router
import '@styles/core/tailwind.css'                  // Tailwind 基础样式
import '@styles/index.scss'                         // 全局样式与主题
import '@icons/system/iconfont.css'                 // 系统图标
import '@/utils/ui/iconify-loader'                 // Iconify 图标（离线）
import '@utils/sys/console.ts'                      // 控制台输出内容
import { setupGlobDirectives } from './directives'
import { setupErrorHandle } from './utils/sys/error-handle'
import { useSystemStore } from './store/modules/system'

document.addEventListener(
  'touchstart',
  function () {},
  { passive: false }
)

async function bootstrap() {
  // 先初始化 store 才能用 systemStore
  const app = createApp(App)
  initStore(app)

  // 预拉取系统信息（应用名称 / Logo / 版权 / 描述）,
  // 让浏览器 <title> / 登录页 / 顶栏在首屏就有正确值,
  // 避免闪现旧名 "Art Design Pro"。
  // 接口失败时 store 内部已兜底,这里不用 try/catch。
  await useSystemStore().fetchSystemInfo()

  initRouter(app)
  setupGlobDirectives(app)
  setupErrorHandle(app)

  app.mount('#app')
}

bootstrap()
