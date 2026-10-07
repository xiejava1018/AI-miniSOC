/**
 * 通知通道 + 用户通知偏好 API（OH-NOT-F2 Phase 2）
 */

import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const CHANNEL_PREFIX = '/api/v1/notification-channels'
const PREF_PREFIX = '/api/v1/notification-preferences'

// ============ 通道 ============

export interface NotificationChannel {
  id: number
  code: string
  name: string
  enabled: boolean
  config_json: Record<string, any>
  created_at: string
  updated_at: string
}

export interface EmailSmtpConfig {
  host: string
  port: number
  user: string
  password: string // 出参为 '***'
  from_addr: string
  use_tls?: boolean
  from_name?: string
  max_retries?: number
  retry_backoff_seconds?: number
}

export interface ChannelTestResult {
  success: boolean
  message: string
  smtp_host: string | null
  smtp_port: number | null
  elapsed_ms: number
}

/** 通道列表 */
export const fetchNotificationChannels = (enabled_only = false) => {
  return httpClient.get<Http.BaseResponse<NotificationChannel[]>>({
    url: `${CHANNEL_PREFIX}`,
    params: { enabled_only },
    keepFullResponse: true
  })
}

/** 更新通道（admin；email 通道传 config_json 完整 SMTP 配置） */
export const updateNotificationChannel = (
  id: number,
  data: { name?: string; enabled?: boolean; config_json?: Record<string, any> }
) => {
  return httpClient.put<Http.BaseResponse<NotificationChannel>>({
    url: `${CHANNEL_PREFIX}/${id}`,
    data,
    keepFullResponse: true
  })
}

/** 测试通道（admin；actual=false 仅 socket 测试，actual=true 真发邮件） */
export const testNotificationChannel = (
  id: number,
  opts?: { to_address?: string; actual?: boolean }
) => {
  return httpClient.post<Http.BaseResponse<ChannelTestResult>>({
    url: `${CHANNEL_PREFIX}/${id}/test`,
    params: { actual: opts?.actual ?? false },
    data: { to_address: opts?.to_address ?? null },
    keepFullResponse: true,
    timeout: 60000
  })
}

// ============ 用户偏好 ============

export interface UserPrefItem {
  type: string
  channel_code: string
  enabled: boolean
}

/** 我的偏好列表（空 = 默认全收） */
export const fetchMyNotificationPrefs = () => {
  return httpClient.get<Http.BaseResponse<{ items: UserPrefItem[] }>>({
    url: `${PREF_PREFIX}/my`,
    keepFullResponse: true
  })
}

/** 更新我对某 (type, channel) 的偏好 */
export const updateMyNotificationPref = (type: string, channelCode: string, enabled: boolean) => {
  return httpClient.put<Http.BaseResponse<UserPrefItem>>({
    url: `${PREF_PREFIX}/my/${encodeURIComponent(type)}/${encodeURIComponent(channelCode)}`,
    data: { enabled },
    keepFullResponse: true
  })
}

/** 已知通知类型（用于偏好页渲染；与后端 email_template_registry 对齐） */
export const NOTIFICATION_TYPE_CATALOG: Array<{ type: string; label: string; desc: string }> = [
  { type: 'push:eol_warning', label: 'EOL 临近', desc: '资产即将到达生命周期终点' },
  { type: 'push:source_down', label: '数据源中断', desc: '数据链路中断超过阈值' },
  { type: 'push:risk_spike', label: '风险评分突变', desc: '资产风险评分显著上升' },
  { type: 'push:shadow_asset', label: '影子资产发现', desc: '新发现未纳管资产' },
  { type: 'task_zombie', label: '任务异常', desc: '后台任务 zombie/失败告警' },
  { type: 'test', label: '测试通知', desc: '管理员手动测试' }
]
