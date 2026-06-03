/**
 * 告警 API
 *
 * 资产详情页 v2 用,Phase 1 阶段后端是 mock,这里只做基本封装。
 * Phase 2 接入 Wazuh 缓存表后会扩展。
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/alerts'

/**
 * 按资产 IP 查询告警列表
 */
export const getAlertsByIp = (
  ip: string,
  params?: Record<string, any>
): Promise<Http.BaseResponse<any[]>> => {
  return httpClient.get({
    url: `${API_PREFIX}`,
    params: { ...params, ip },
    keepFullResponse: true
  })
}

/**
 * 告警统计(总数/按等级分组)
 */
export const getAlertStatistics = (params?: Record<string, any>): Promise<Http.BaseResponse<any>> => {
  return httpClient.get({
    url: `${API_PREFIX}/statistics`,
    params,
    keepFullResponse: true
  })
}
