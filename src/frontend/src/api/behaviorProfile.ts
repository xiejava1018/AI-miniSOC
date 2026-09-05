/**
 * 行为画像 API（docs/design/2026-09-05-用户IP行为画像-方案设计.md §9.4）
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient
const API_PREFIX = '/api/v1'

/** 全部主体画像摘要（列表） */
export const getBehaviorProfiles = (params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/list`,
    params,
    keepFullResponse: true
  })
}

/** 单主体聚合画像 */
export const getBehaviorProfile = (ip: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}`,
    params,
    keepFullResponse: true
  })
}

/** 域名 TOP N 下钻 */
export const getBehaviorDomains = (ip: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/domains`,
    params,
    keepFullResponse: true
  })
}

/** 多日趋势 */
export const getBehaviorTrend = (ip: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/trend`,
    params,
    keepFullResponse: true
  })
}

/** 当日实时重算（写操作，admin/operator） */
export const refreshBehaviorProfile = (ip: string): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/behavior-profile/${ip}/refresh`,
    keepFullResponse: true
  })
}

/** 风险画像（层3：告警分级/规则榜/漏洞/端口/评分趋势） */
export const getBehaviorRisk = (ip: string): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/risk`,
    keepFullResponse: true
  })
}

/** 异常判定信号（层5） */
export const getBehaviorAnomalies = (ip: string): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/anomalies`,
    keepFullResponse: true
  })
}

/** 关系画像（层4：登录出/入站、账号归一化、设备共享度、外部攻击源） */
export const getBehaviorRelations = (ip: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/relations`,
    params,
    keepFullResponse: true
  })
}

/** 单域名逐日明细（下钻） */
export const getBehaviorDomainDaily = (
  ip: string,
  domain: string,
  params?: Record<string, any>
): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/domains/${encodeURIComponent(domain)}/daily`,
    params,
    keepFullResponse: true
  })
}

/** 双 IP 画像对比 */
export const compareBehaviorProfiles = (params: {
  a: string
  b: string
  days?: number
}): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/compare`,
    params,
    keepFullResponse: true
  })
}

/** LLM 画像摘要 + 异常解读（降级走规则模板，source 字段标明） */
export const getBehaviorAiSummary = (ip: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/behavior-profile/${ip}/ai-summary`,
    params,
    keepFullResponse: true,
    timeout: 180000
  })
}

/** 导出画像 HTML 报告（返回 blob 下载，token 从 user store 取） */
export const exportBehaviorProfile = async (ip: string, days = 7): Promise<void> => {
  const { useUserStore } = await import('@/store/modules/user')
  const resp = await fetch(
    `${API_PREFIX}/behavior-profile/${ip}/export?days=${days}`,
    { headers: { Authorization: `Bearer ${(useUserStore() as any).accessToken || ''}` } }
  )
  if (!resp.ok) throw new Error('export failed')
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `behavior-profile-${ip}.html`
  a.click()
  URL.revokeObjectURL(url)
}
