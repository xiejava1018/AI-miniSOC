import request from '@/utils/http'

const BASE = '/api/v1/system-configs'

/** 分类列表 */
export function getConfigCategories() {
  return request.get<Api.SystemConfig.CategoryItem[]>({
    url: `${BASE}/categories`,
  })
}

/** 按分类取全部配置（不分页） */
export function getConfigsByCategory(category: string) {
  return request.get<Api.SystemConfig.ConfigItem[]>({
    url: `${BASE}/by-category/${encodeURIComponent(category)}`,
  })
}

/** 分页查询 */
export function getConfigList(params?: Api.SystemConfig.ConfigSearchParams) {
  return request.get({
    url: BASE,
    params: {
      page: (params as any)?.current ?? (params as any)?.page ?? 1,
      page_size: (params as any)?.size ?? (params as any)?.page_size ?? 20,
      category: (params as any)?.category,
      search: (params as any)?.search,
    },
    keepFullResponse: true,
  })
}

/** 单条详情 */
export function getConfig(id: number) {
  return request.get<Api.SystemConfig.ConfigItem>({
    url: `${BASE}/${id}`,
  })
}

/** 新增 */
export function addConfig(data: Api.SystemConfig.ConfigPayload) {
  return request.post({
    url: BASE,
    data,
    showSuccessMessage: true,
    successMessage: '新增成功',
  })
}

/** 更新 */
export function updateConfig(id: number, data: Partial<Api.SystemConfig.ConfigPayload>) {
  return request.put({
    url: `${BASE}/${id}`,
    data,
    showSuccessMessage: true,
    successMessage: '更新成功',
  })
}

/** 删除 */
export function deleteConfig(id: number) {
  return request.del({
    url: `${BASE}/${id}`,
    showSuccessMessage: true,
    successMessage: '删除成功',
  })
}
