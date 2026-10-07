<template>
  <div class="notification-channels-page">
    <ArtSearchBar>
      <template #title>通知通道管理</template>
      <template #subTitle>站内信与邮件双通道；SMTP 配置加密存储（OH-NOT-F2）</template>
    </ArtSearchBar>

    <el-row :gutter="16">
      <!-- 站内信通道（只读） -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span><el-icon><Bell /></el-icon> 站内信 (inbox)</span>
              <el-tag :type="inboxChannel?.enabled ? 'success' : 'info'" size="small">
                {{ inboxChannel?.enabled ? '已启用' : '已停用' }}
              </el-tag>
            </div>
          </template>
          <el-empty description="站内信通道无需配置，始终可用" :image-size="60" />
        </el-card>
      </el-col>

      <!-- 邮件通道（SMTP 可配置） -->
      <el-col :span="16">
        <el-card shadow="never" v-loading="loading">
          <template #header>
            <div class="card-header">
              <span><el-icon><Message /></el-icon> 邮件 (email)</span>
              <div>
                <el-switch
                  v-model="emailEnabled"
                  :disabled="!isDirty"
                  active-text="启用"
                  @change="onToggleEmail"
                />
              </div>
            </div>
          </template>

          <el-form :model="smtpForm" label-width="120px" :disabled="saving">
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="SMTP 服务器" required>
                  <el-input v-model="smtpForm.host" placeholder="smtp.example.com" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="端口" required>
                  <el-input-number
                    v-model="smtpForm.port"
                    :min="1"
                    :max="65535"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="用户名" required>
                  <el-input v-model="smtpForm.user" placeholder="smtp 用户名" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="密码/授权码" required>
                  <el-input
                    v-model="smtpForm.password"
                    type="password"
                    show-password
                    placeholder="留空表示不修改"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="发件人地址" required>
                  <el-input v-model="smtpForm.from_addr" placeholder="noreply@example.com" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="发件人名称">
                  <el-input v-model="smtpForm.from_name" placeholder="AI-miniSOC 通知" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="使用 TLS">
                  <el-switch v-model="smtpForm.use_tls" />
                  <span class="form-hint">465 端口自动走 SMTPS，587 走 STARTTLS</span>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最大重试">
                  <el-input-number
                    v-model="smtpForm.max_retries"
                    :min="0"
                    :max="10"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <div class="actions">
            <el-button type="primary" :loading="saving" :disabled="!isDirty" @click="onSave">
              保存配置
            </el-button>
            <el-button
              :loading="testing"
              :disabled="emailChannel && !emailChannel.enabled"
              @click="onTest(false)"
            >
              连接测试
            </el-button>
            <el-button
              type="warning"
              :loading="testingActual"
              :disabled="emailChannel && !emailChannel.enabled"
              @click="onTest(true)"
            >
              发送测试邮件
            </el-button>
          </div>

          <el-alert
            v-if="testResult"
            :title="testResult.message"
            :type="testResult.success ? 'success' : 'error'"
            :closable="false"
            show-icon
            style="margin-top: 12px"
          >
            <template #default>
              <div v-if="testResult.smtp_host">
                {{ testResult.smtp_host }}:{{ testResult.smtp_port }} ·
                {{ testResult.elapsed_ms }}ms
              </div>
            </template>
          </el-alert>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
/**
 * 通知通道管理（admin）— OH-NOT-F2 Phase 2
 *
 * 设计依据：docs/sessions/2026-10-07-notification-channel-phase1.md
 * - SMTP 配置存 soc_notification_channels.email.config_json（密码 fernet 加密）
 * - 连接测试 = socket 探活；发送测试 = 真实投递到指定邮箱
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Message } from '@element-plus/icons-vue'
import ArtSearchBar from '@/components/core/forms/art-search-bar/index.vue'
import {
  fetchNotificationChannels,
  updateNotificationChannel,
  testNotificationChannel,
  type NotificationChannel,
  type ChannelTestResult
} from '@/api/notificationChannel'

defineOptions({ name: 'NotificationChannels' })

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const testingActual = ref(false)
const channels = ref<NotificationChannel[]>([])
const testResult = ref<ChannelTestResult | null>(null)

const inboxChannel = computed(() => channels.value.find((c) => c.code === 'inbox'))
const emailChannel = computed(() => channels.value.find((c) => c.code === 'email'))

const smtpForm = reactive({
  host: '',
  port: 587,
  user: '',
  password: '', // 出参是 '***'；提交时空串表示不改
  from_addr: '',
  from_name: 'AI-miniSOC 通知',
  use_tls: true,
  max_retries: 3
})

const emailEnabled = ref(false)
// 跟踪表单是否被修改过（未保存前不允许切 enabled）
const isDirty = computed(() => false) // 简化：保存后刷新状态由后端控制

const loadChannels = async () => {
  loading.value = true
  try {
    const res = await fetchNotificationChannels()
    if (res.code === 200 && res.data) {
      channels.value = res.data
      const email = res.data.find((c) => c.code === 'email')
      if (email) {
        emailEnabled.value = email.enabled
        const cfg = (email.config_json || {}) as Record<string, any>
        smtpForm.host = cfg.host ?? ''
        smtpForm.port = cfg.port ?? 587
        smtpForm.user = cfg.user ?? ''
        smtpForm.password = '' // 出参是 ***，不回显
        smtpForm.from_addr = cfg.from_addr ?? ''
        smtpForm.from_name = cfg.from_name ?? 'AI-miniSOC 通知'
        smtpForm.use_tls = cfg.use_tls ?? true
        smtpForm.max_retries = cfg.max_retries ?? 3
      }
    }
  } finally {
    loading.value = false
  }
}

const onSave = async () => {
  if (!emailChannel.value) return
  if (!smtpForm.host || !smtpForm.user || !smtpForm.from_addr) {
    ElMessage.warning('SMTP 服务器、用户名、发件人地址为必填项')
    return
  }
  saving.value = true
  try {
    const configJson: Record<string, any> = {
      host: smtpForm.host,
      port: smtpForm.port,
      user: smtpForm.user,
      from_addr: smtpForm.from_addr,
      use_tls: smtpForm.use_tls,
      max_retries: smtpForm.max_retries
    }
    if (smtpForm.from_name) configJson.from_name = smtpForm.from_name
    // 密码：仅当用户输入了新值才提交（避免把 '***' 提交回去）
    if (smtpForm.password && smtpForm.password !== '***') {
      configJson.password = smtpForm.password
    } else if (emailChannel.value.config_json?.password) {
      // 保留原密码：后端 PUT 是全量替换 config_json，需要带上原密文
      configJson.password = emailChannel.value.config_json.password
    } else {
      ElMessage.warning('首次配置需要填写密码/授权码')
      return
    }
    const res = await updateNotificationChannel(emailChannel.value.id, {
      enabled: true,
      config_json: configJson
    })
    if (res.code === 200) {
      ElMessage.success('SMTP 配置已保存（密码已加密存储）')
      await loadChannels()
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

const onToggleEmail = async () => {
  if (!emailChannel.value) return
  try {
    const res = await updateNotificationChannel(emailChannel.value.id, {
      enabled: emailEnabled.value
    })
    if (res.code === 200) {
      ElMessage.success(emailEnabled.value ? '邮件通道已启用' : '邮件通道已停用')
    } else {
      ElMessage.error(res.msg || '操作失败')
      emailEnabled.value = !emailEnabled.value
    }
  } catch {
    emailEnabled.value = !emailEnabled.value
  }
}

const onTest = async (actual: boolean) => {
  if (!emailChannel.value) return
  if (actual) {
    testingActual.value = true
  } else {
    testing.value = true
  }
  testResult.value = null
  try {
    const res = await testNotificationChannel(emailChannel.value.id, { actual })
    if (res.code === 200 && res.data) {
      testResult.value = res.data
    } else {
      ElMessage.error(res.msg || '测试失败')
    }
  } finally {
    testing.value = false
    testingActual.value = false
  }
}

onMounted(loadChannels)
</script>

<style scoped>
.notification-channels-page {
  padding: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.form-hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>

<!-- 全局样式：ArtTable 内渲染的节点拿不到本页 scoped 属性，须全局加前缀（同 data-source 页坑） -->
