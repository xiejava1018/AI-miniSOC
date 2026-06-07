<template>
  <ElConfigProvider
    size="default"
    :locale="zh"
    :z-index="3000"
    :card="{
      shadow: 'never'
    }"
  >
    <RouterView></RouterView>
    <!-- Art Bot + 站内通知全局挂载（上游 art-design-pro 模式） -->
    <ArtChatWindow />
    <ArtNotification v-model:value="noticeVisible" />
  </ElConfigProvider>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import zh from 'element-plus/es/locale/lang/zh-cn'
  import { useUserStore } from '@/store/modules/user'
  import { useNotificationStore } from '@/store/modules/notification'
  import { useDictStore } from '@/store/modules/dict'
  import ArtChatWindow from '@/components/core/layouts/art-chat-window/index.vue'
  import ArtNotification from '@/components/core/layouts/art-notification/index.vue'
  import { systemUpgrade } from './utils/sys'
  import { toggleTransition } from './utils/ui/animation'
  import { checkStorageCompatibility } from './utils/storage'
  import { initializeTheme } from './hooks/core/useTheme'

  const userStore = useUserStore()
  const notifStore = useNotificationStore()
  const dictStore = useDictStore()
  const noticeVisible = ref(false)

  onBeforeMount(() => {
    toggleTransition(true)
    initializeTheme()
  })

  onMounted(() => {
    checkStorageCompatibility()
    toggleTransition(false)
    systemUpgrade()
    // 登录态时启动站内通知 WebSocket + 拉未读数
    if (userStore.accessToken) {
      notifStore.connect()
      // 字典走 Pinia 内存缓存(page refresh → lost)，已登录态下若缓存为空则自动加载
      if (!dictStore.loaded) {
        dictStore.loadAll()
      }
    }
  })

  // 登录/登出变化时联动 WS
  watch(
    () => userStore.accessToken,
    (token, old) => {
      if (token && !old) {
        notifStore.connect()
        // 新登录态下若字典未加载则自动加载
        if (!dictStore.loaded) {
          dictStore.loadAll()
        }
      } else if (!token && old) {
        notifStore.disconnect()
      }
    }
  )
</script>
