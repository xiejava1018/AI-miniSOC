<!--
  站内通知面板

  来源：art-design-pro 上游 layouts/art-notification（MIT）
  本地化：去掉 i18n（项目已移除 vue-i18n）+ 接入真实后端通知 API
-->
<template>
  <div
    class="art-notification-panel art-card-sm !shadow-xl"
    :style="{
      transform: show ? 'scaleY(1)' : 'scaleY(0.9)',
      opacity: show ? 1 : 0
    }"
    v-show="visible"
    @click.stop
  >
    <div class="flex-cb px-3.5 mt-3.5">
      <span class="text-base font-medium text-g-800">通知</span>
      <span
        v-if="unreadCount > 0"
        class="text-xs text-g-800 px-1.5 py-1 c-p select-none rounded hover:bg-g-200"
        @click="markAllRead"
      >
        全部已读
      </span>
    </div>

    <ul class="box-border flex items-end w-full h-12.5 px-3.5 border-b-d">
      <li
        class="h-12 leading-12 mr-5 overflow-hidden text-[13px] text-g-700 c-p select-none"
        :class="{ 'bar-active': true }"
      >
        通知 ({{ unreadCount }})
      </li>
    </ul>

    <div class="w-full h-[calc(100%-95px)]">
      <div class="h-[calc(100%-60px)] overflow-y-scroll scrollbar-thin">
        <ul v-show="true">
          <li
            v-for="item in noticeList"
            :key="item.id"
            class="box-border flex-c px-3.5 py-3.5 c-p last:border-b-0 hover:bg-g-200/60"
            :class="{ 'is-unread': !item.is_read }"
            @click="onItemClick(item)"
          >
            <div
              class="size-9 leading-9 text-center rounded-lg flex-cc"
              :class="[getNoticeStyle(item.type).iconClass]"
            >
              <ArtSvgIcon class="text-lg !bg-transparent" :icon="getNoticeStyle(item.type).icon" />
            </div>
            <div class="w-[calc(100%-45px)] ml-3.5">
              <h4 class="text-sm font-normal leading-5.5 text-g-900">{{ item.title }}</h4>
              <p class="mt-1.5 text-xs text-g-500 line-clamp-2">
                {{ item.content || formatTime(item.created_at) }}
              </p>
            </div>
          </li>
        </ul>

        <!-- 空状态 -->
        <div
          v-show="noticeList.length === 0"
          class="relative top-25 h-full text-g-500 text-center !bg-transparent"
        >
          <ArtSvgIcon icon="system-uicons:inbox" class="text-5xl" />
          <p class="mt-3.5 text-xs !bg-transparent">暂无通知</p>
        </div>
      </div>

      <div class="relative box-border w-full px-3.5">
        <ElButton class="w-full mt-3" @click="closePanel" v-ripple>关闭</ElButton>
      </div>
    </div>

    <div class="h-25"></div>
  </div>
</template>

<script setup lang="ts">
  import { ref, watch, onMounted, onUnmounted } from 'vue'
  import { storeToRefs } from 'pinia'
  import { useNotificationStore } from '@/store/modules/notification'
  import { mittBus } from '@/utils/sys'
  import type { NotificationItem } from '@/api/notification'

  defineOptions({ name: 'ArtNotification' })

  const props = defineProps<{ value: boolean }>()
  const emit = defineEmits<{ 'update:value': [v: boolean] }>()

  const notifStore = useNotificationStore()
  const { list: noticeList, unreadCount } = storeToRefs(notifStore)

  const show = ref(false)
  const visible = ref(false)

  // 通知类型 → icon + 配色（沿用上游设计系统，扩展 type 覆盖我们的 alert/ai_done/test）
  const noticeStyleMap: Record<
    string,
    { icon: string; iconClass: string }
  > = {
    email: { icon: 'ri:mail-line', iconClass: 'bg-warning/12 text-warning' },
    message: { icon: 'ri:volume-down-line', iconClass: 'bg-success/12 text-success' },
    collection: { icon: 'ri:heart-3-line', iconClass: 'bg-danger/12 text-danger' },
    user: { icon: 'ri:volume-down-line', iconClass: 'bg-info/12 text-info' },
    notice: { icon: 'ri:notification-3-line', iconClass: 'bg-theme/12 text-theme' },
    // AI-miniSOC 扩展
    alert: { icon: 'ri:alarm-warning-line', iconClass: 'bg-danger/12 text-danger' },
    ai_done: { icon: 'ri:robot-2-line', iconClass: 'bg-success/12 text-success' },
    system: { icon: 'ri:settings-3-line', iconClass: 'bg-info/12 text-info' },
    test: { icon: 'ri:test-tube-line', iconClass: 'bg-warning/12 text-warning' }
  }

  const getNoticeStyle = (type: string) => {
    return (
      noticeStyleMap[type] || {
        icon: 'ri:notification-3-line',
        iconClass: 'bg-theme/12 text-theme'
      }
    )
  }

  // 显示/关闭动画
  const showNotice = (open: boolean) => {
    if (open) {
      visible.value = true
      setTimeout(() => {
        show.value = true
      }, 5)
    } else {
      show.value = false
      setTimeout(() => {
        visible.value = false
      }, 350)
    }
  }

  watch(
    () => props.value,
    (v) => {
      showNotice(v)
      if (v) {
        // 打开时拉一次最新
        void notifStore.loadUnread()
        void notifStore.loadList()
      }
    }
  )

  function closePanel(): void {
    emit('update:value', false)
  }

  async function onItemClick(n: NotificationItem): Promise<void> {
    if (!n.is_read) {
      await notifStore.markRead(n.id)
    }
    if (n.link) {
      window.location.href = n.link
    }
  }

  async function markAllRead(): Promise<void> {
    await notifStore.markAllRead()
  }

  function formatTime(iso: string): string {
    try {
      const d = new Date(iso)
      return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    } catch {
      return iso
    }
  }

  onMounted(() => {
    void notifStore.loadUnread()
    mittBus.on('openNotice', openFromBus)
  })

  onUnmounted(() => {
    mittBus.off('openNotice', openFromBus)
  })

  function openFromBus(): void {
    emit('update:value', true)
  }
</script>

<style scoped>
  @reference '@styles/core/tailwind.css';

  .art-notification-panel {
    @apply absolute
    top-14.5
    right-5
    w-90
    h-125
    overflow-hidden
    transition-all
    duration-300
    origin-top
    will-change-[top,left]
    max-[640px]:top-[65px]
    max-[640px]:right-0
    max-[640px]:w-full
    max-[640px]:h-[80vh];
  }

  .bar-active {
    color: var(--theme-color) !important;
    border-bottom: 2px solid var(--theme-color);
  }

  .scrollbar-thin::-webkit-scrollbar {
    width: 5px !important;
  }

  .dark .scrollbar-thin::-webkit-scrollbar-track {
    background-color: var(--default-box-color);
  }

  .dark .scrollbar-thin::-webkit-scrollbar-thumb {
    background-color: #222 !important;
  }

  .is-unread {
    background: var(--el-color-primary-light-9);
  }
</style>
