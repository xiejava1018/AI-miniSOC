<template>
  <div class="notification-preferences-page">
    <ArtSearchBar>
      <template #title>通知偏好</template>
      <template #subTitle>按通知类型 × 通道精细控制；未配置的类型默认全收（OH-NOT-F2）</template>
    </ArtSearchBar>

    <el-card shadow="never" v-loading="loading">
      <el-table :data="rows" border style="width: 100%">
        <el-table-column prop="type" label="类型" width="180">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="label" label="名称" width="140" />
        <el-table-column prop="desc" label="说明" min-width="200" />
        <el-table-column label="站内信 (inbox)" width="130" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="getPref(row.type, 'inbox')"
              :loading="savingKey === `${row.type}:inbox`"
              @change="(v: any) => onToggle(row.type, 'inbox', v as boolean)"
            />
          </template>
        </el-table-column>
        <el-table-column label="邮件 (email)" width="130" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="getPref(row.type, 'email')"
              :loading="savingKey === `${row.type}:email`"
              @change="(v: any) => onToggle(row.type, 'email', v as boolean)"
            />
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 12px"
        title="开关默认为开（未配置 = 接收）；关闭后该类型通知不再通过对应通道投递给你"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * 用户通知偏好页 — OH-NOT-F2 Phase 2
 *
 * 后端语义（soc_notification_user_prefs）：
 * - 默认空表 = 所有 (type, channel) 全收（X1 矩阵）
 * - enabled=false 行 = 用户主动禁用该组合
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ArtSearchBar from '@/components/core/forms/art-search-bar/index.vue'
import {
  fetchMyNotificationPrefs,
  updateMyNotificationPref,
  NOTIFICATION_TYPE_CATALOG,
  type UserPrefItem
} from '@/api/notificationChannel'

defineOptions({ name: 'NotificationPreferences' })

const loading = ref(false)
const savingKey = ref('')
const prefs = ref<UserPrefItem[]>([])

const rows = NOTIFICATION_TYPE_CATALOG

/** 读取偏好；无记录 = 默认 true（全收） */
const getPref = (type: string, channel: string): boolean => {
  const p = prefs.value.find((x) => x.type === type && x.channel_code === channel)
  return p ? p.enabled : true
}

const onToggle = async (type: string, channel: string, enabled: boolean) => {
  savingKey.value = `${type}:${channel}`
  try {
    const res = await updateMyNotificationPref(type, channel, enabled)
    if (res.code === 200 && res.data) {
      const idx = prefs.value.findIndex(
        (x) => x.type === type && x.channel_code === channel
      )
      if (idx >= 0) {
        prefs.value[idx] = res.data
      } else {
        prefs.value.push(res.data)
      }
      ElMessage.success(enabled ? '已开启接收' : '已关闭该通道投递')
    } else {
      ElMessage.error(res.msg || '操作失败')
    }
  } finally {
    savingKey.value = ''
  }
}

const loadPrefs = async () => {
  loading.value = true
  try {
    const res = await fetchMyNotificationPrefs()
    if (res.code === 200 && res.data) {
      prefs.value = res.data.items || []
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadPrefs)
</script>

<style scoped>
.notification-preferences-page {
  padding: 16px;
}
</style>
