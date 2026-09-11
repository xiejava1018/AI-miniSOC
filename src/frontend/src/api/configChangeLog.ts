/**
 * 配置变更审计 API（X1E-11 配置中心）
 */
import request from '@/utils/http'

const BASE = '/api/v1/config-change-logs'

export function getConfigChangeLogs(params?: Api.ConfigChangeLog.SearchParams) {
  return request.get({
    url: BASE,
    params: {
      page: (params as any)?.page ?? 1,
      page_size: (params as any)?.page_size ?? 20,
      target_type: (params as any)?.target_type,
      action: (params as any)?.action,
      search: (params as any)?.search,
    },
    keepFullResponse: true,
  })
}