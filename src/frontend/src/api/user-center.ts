import request from '@/utils/http'

/**
 * 用户中心 API（PR1 后端已就绪）
 *
 * - GET/PUT  /api/v1/users/me              基本资料
 * - POST     /api/v1/users/me/change-password
 * - GET/POST /api/v1/users/me/mcp-keys     MCP Key 自助管理
 * - POST     /api/v1/users/me/mcp-keys/{id}/extend
 * - DELETE   /api/v1/users/me/mcp-keys/{id}
 *
 * envelope：HTTP 恒 200，业务码在 body.code（拦截器已处理）
 */

/** 我的完整资料（GET /users/me） */
export interface MyProfile {
  id: number
  username: string
  nick_name?: string | null
  email?: string | null
  phone?: string | null
  avatar?: string | null
  gender?: number | null
  role_code?: string | null
  role_name?: string | null
  department_id?: number | null
  department_name?: string | null
  status?: string | null
  last_login?: string | null
  created_at?: string | null
}

/** MCP Key 列表项（永不返回明文） */
export interface McpKeyItem {
  id: number
  name: string
  /** 明文前缀，如 sk-mcp-Xk9f */
  key_prefix: string
  /** active / revoked（过期为运行时判定：active && days_remaining===0） */
  status: 'active' | 'revoked'
  days_remaining: number | null
  expires_at: string | null
  last_used_at: string | null
  created_at: string | null
}

/** 申请成功响应（含一次性明文 key —— 仅此一次返回） */
export interface McpKeyCreated extends McpKeyItem {
  key: string
}

/** 获取我的完整资料 */
export function fetchGetMyProfile() {
  return request.get<MyProfile>({
    url: '/api/v1/users/me',
    showErrorMessage: false
  })
}

/** 更新我的基本资料（白名单字段：nick_name/phone/email/avatar/gender） */
export function fetchUpdateMyProfile(
  data: Partial<Pick<MyProfile, 'nick_name' | 'phone' | 'email' | 'avatar' | 'gender'>>
) {
  return request.put<MyProfile>({
    url: '/api/v1/users/me',
    data,
    showErrorMessage: false
  })
}

/** 修改密码（旧密码错 → code 401；新密码强度弱 → code 422） */
export function fetchChangeMyPassword(data: { old_password: string; new_password: string }) {
  return request.post<void>({
    url: '/api/v1/users/me/change-password',
    data,
    showErrorMessage: false
  })
}

/** 我的 Key 列表 */
export function fetchGetMyMcpKeys() {
  return request.get<McpKeyItem[]>({
    url: '/api/v1/users/me/mcp-keys',
    showErrorMessage: false
  })
}

/** 申请新 Key（返回一次性明文） */
export function fetchCreateMyMcpKey(data: { name: string; validity_days: number }) {
  return request.post<McpKeyCreated>({
    url: '/api/v1/users/me/mcp-keys',
    data,
    showErrorMessage: false
  })
}

/** 延期 Key（仅 active 可延期） */
export function fetchExtendMyMcpKey(keyId: number, new_validity_days: number) {
  return request.post<McpKeyItem>({
    url: `/api/v1/users/me/mcp-keys/${keyId}/extend`,
    data: { new_validity_days },
    showErrorMessage: false
  })
}

/** 注销 Key（幂等，即时生效） */
export function fetchRevokeMyMcpKey(keyId: number) {
  return request.del<McpKeyItem>({
    url: `/api/v1/users/me/mcp-keys/${keyId}`,
    showErrorMessage: false
  })
}

/* ------------------------------------------------------------------ *
 * admin 侧（PR3 补充）
 * ------------------------------------------------------------------ */

/** 查看指定用户 Key 列表（仅 admin 可见） */
export function fetchGetUserMcpKeys(userId: number) {
  return request.get<McpKeyItem[]>({
    url: `/api/v1/users/${userId}/mcp-keys`,
    showErrorMessage: false
  })
}

/** admin 代发新 Key（返回一次性明文；key_admin 已负责保密转交） */
export function fetchAdminCreateMcpKey(userId: number, data: { name: string; validity_days: number }) {
  return request.post<McpKeyCreated>({
    url: `/api/v1/users/${userId}/mcp-keys`,
    data,
    showErrorMessage: false
  })
}

/** admin 强制注销指定用户的 Key */
export function fetchAdminRevokeMcpKey(userId: number, keyId: number) {
  return request.del<McpKeyItem>({
    url: `/api/v1/users/${userId}/mcp-keys/${keyId}`,
    showErrorMessage: false
  })
}
