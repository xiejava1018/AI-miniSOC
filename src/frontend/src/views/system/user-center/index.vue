<!-- 个人中心：基本资料 / 安全设置 / MCP 接入（PR2 重构，替换原 demo 假页） -->
<template>
  <div class="w-full h-full p-0 bg-transparent border-none shadow-none">
    <div class="relative flex-b mt-2.5 max-md:block max-md:mt-1">
      <!-- 左侧个人信息卡（真实数据） -->
      <div class="w-112 mr-5 max-md:w-full max-md:mr-0">
        <div class="art-card-sm relative p-9 pb-6 overflow-hidden text-center">
          <img class="absolute top-0 left-0 w-full h-50 object-cover" src="@imgs/user/bg.webp" />
          <img
            class="relative z-10 w-20 h-20 mt-30 mx-auto object-cover border-2 border-white rounded-full"
            :src="displayedAvatar"
            alt="avatar"
            @error="onAvatarError"
          />
          <h2 class="mt-5 text-xl font-normal">{{ displayName }}</h2>
          <div class="flex-c justify-center gap-2 mt-3">
            <ElTag size="small" effect="light" :type="roleTagType">
              {{ profile?.role_name || profile?.role_code || '未分配角色' }}
            </ElTag>
            <ElTag v-if="profile?.status !== 'active'" size="small" type="danger" effect="light">
              {{ profile?.status }}
            </ElTag>
          </div>

          <div class="w-75 mx-auto mt-7.5 text-left">
            <div class="mt-2.5">
              <ArtSvgIcon icon="ri:user-3-line" class="text-g-700" />
              <span class="ml-2 text-sm">{{ profile?.username || '-' }}</span>
            </div>
            <div class="mt-2.5">
              <ArtSvgIcon icon="ri:building-line" class="text-g-700" />
              <span class="ml-2 text-sm">{{ profile?.department_name || '未分配部门' }}</span>
            </div>
            <div class="mt-2.5">
              <ArtSvgIcon icon="ri:mail-line" class="text-g-700" />
              <span class="ml-2 text-sm">{{ profile?.email || '未设置邮箱' }}</span>
            </div>
            <div class="mt-2.5">
              <ArtSvgIcon icon="ri:time-line" class="text-g-700" />
              <span class="ml-2 text-sm">最后登录：{{ formatTime(profile?.last_login) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧 Tabs -->
      <div class="flex-1 overflow-hidden max-md:w-full max-md:mt-3.5">
        <div class="art-card-sm p-5">
          <ElTabs v-model="activeTab">
            <ElTabPane name="profile">
              <template #label>
                <span class="flex-c"
                  ><ArtSvgIcon icon="ri:user-settings-line" class="mr-1" /> 基本资料</span
                >
              </template>
              <ProfileTab v-if="profile" :profile="profile" @saved="onProfileSaved" />
            </ElTabPane>
            <ElTabPane name="security">
              <template #label>
                <span class="flex-c"
                  ><ArtSvgIcon icon="ri:shield-keyhole-line" class="mr-1" /> 安全设置</span
                >
              </template>
              <SecurityTab v-if="profile" :profile="profile" />
            </ElTabPane>
            <ElTabPane name="mcp">
              <template #label>
                <span class="flex-c"
                  ><ArtSvgIcon icon="ri:key-2-line" class="mr-1" /> MCP 接入</span
                >
              </template>
              <McpKeyTab :role-code="profile?.role_code" />
            </ElTabPane>
          </ElTabs>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import ProfileTab from './components/ProfileTab.vue'
  import SecurityTab from './components/SecurityTab.vue'
  import McpKeyTab from './components/McpKeyTab.vue'
  import { fetchGetMyProfile, type MyProfile } from '@/api/user-center'
  import { useUserStore } from '@/store/modules/user'
  import defaultAvatar from '@imgs/user/avatar.webp'

  defineOptions({ name: 'UserCenter' })

  const userStore = useUserStore()
  const activeTab = ref('profile')
  const profile = ref<MyProfile | null>(null)

  const loadProfile = async () => {
    try {
      profile.value = await fetchGetMyProfile()
    } catch (e) {
      console.error('加载个人资料失败', e)
    }
  }

  onMounted(loadProfile)

  /** 资料保存成功 → 同步 store（pinia persist 自动写 localStorage，F5 不回旧值） */
  const onProfileSaved = (latest: MyProfile) => {
    profile.value = latest
    const old = userStore.getUserInfo || {}
    userStore.setUserInfo({
      ...old,
      userName: latest.username,
      nickName: latest.nick_name || old.nickName,
      email: latest.email || old.email,
      phone: latest.phone || old.phone,
      avatar: latest.avatar || '',
      gender: latest.gender ?? old.gender
    } as Api.Auth.UserInfo)
  }

  // 头像展示（失效外链兜底回默认头像）
  const displayedAvatar = ref(defaultAvatar)
  const onAvatarError = () => {
    displayedAvatar.value = defaultAvatar
  }
  watch(
    () => profile.value?.avatar,
    (next) => {
      displayedAvatar.value =
        next && !['/src/', '@/'].some((p) => next.startsWith(p)) ? next : defaultAvatar
    },
    { immediate: true }
  )

  const displayName = computed(
    () => profile.value?.nick_name || profile.value?.username || '未命名用户'
  )

  const roleTagType = computed(() => {
    const code = profile.value?.role_code
    if (code === 'admin') return 'danger'
    if (code === 'operator') return 'warning'
    return 'info'
  })

  const formatTime = (t?: string | null): string => {
    if (!t) return '-'
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return t
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
</script>
