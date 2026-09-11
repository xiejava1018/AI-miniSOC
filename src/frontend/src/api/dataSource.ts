/**
 * 数据源管理 API（X1E-11 配置中心）
 *
 * 设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.5
 */
import request from '@/utils/http'

const BASE = '/api/v1/data-sources'

/** 列表 */
export function getDataSourceList(params?: Api.DataSource.SearchParams) {
  return request.get({
    url: BASE,
    params: {
      page: (params as any)?.page ?? 1,
      page_size: (params as any)?.page_size ?? 20,
      source_type: (params as any)?.source_type,
      search: (params as any)?.search,
    },
    keepFullResponse: true,
  })
}

/** 支持的 source_type 枚举与字段模板 */
export function getDataSourceTypes() {
  return request.get<Api.DataSource.TypeItem[]>({
    url: `${BASE}/types`,
  })
}

/** 各类型当前生效来源（用于界面"当前生效来源"提示） */
export function getResolveStatus() {
  return request.get<Api.DataSource.ResolveStatusItem[]>({
    url: `${BASE}/resolve-status`,
  })
}

/** 详情 */
export function getDataSource(id: number) {
  return request.get<Api.DataSource.Item>({
    url: `${BASE}/${id}`,
  })
}

/** 新增 */
export function addDataSource(data: Api.DataSource.Payload) {
  return request.post({
    url: BASE,
    data,
    showSuccessMessage: true,
    successMessage: '新增成功',
  })
}

/** 更新 */
export function updateDataSource(id: number, data: Api.DataSource.UpdatePayload) {
  return request.put({
    url: `${BASE}/${id}`,
    data,
    showSuccessMessage: true,
    successMessage: '更新成功',
  })
}

/** 删除 */
export function deleteDataSource(id: number) {
  return request.del({
    url: `${BASE}/${id}`,
    showSuccessMessage: true,
    successMessage: '删除成功',
  })
}

/** 启停 */
export function toggleDataSource(id: number, enabled: boolean) {
  return request.patch({
    url: `${BASE}/${id}/enabled`,
    data: { enabled },
    showSuccessMessage: true,
    successMessage: enabled ? '已启用' : '已停用',
  })
}

/** 设为默认 */
export function setDefaultDataSource(id: number) {
  return request.post({
    url: `${BASE}/${id}/set-default`,
    showSuccessMessage: true,
    successMessage: '已设为默认',
  })
}

/** 测试连接 */
export function testDataSourceConnection(payload: { id?: number; draft?: Api.DataSource.Payload }) {
  return request.post<Api.DataSource.TestResult>({
    url: `${BASE}/test`,
    data: payload,
  })
}