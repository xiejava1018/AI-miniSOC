/**
 * 配置 Schema API（X1E-11 配置中心）
 *
 * 配置中心动态渲染表单所需的元信息。
 */
import request from '@/utils/http'

const BASE = '/api/v1/config-schemas'

/** 全部 Schema（可按 category 过滤） */
export function getConfigSchemas(category?: string) {
  return request.get({
    url: BASE,
    params: category ? { category } : undefined,
  })
}