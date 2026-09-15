import request from '@/utils/http'

const BS_BASE = '/api/v1/business-systems'

export interface BusinessSystemItem {
  id: string
  code: string
  name: string
  criticality: string
  owner?: string | null
  owner_contact?: string | null
  owner_id?: number | null
  department_id?: number | null
  department_name?: string | null
  description?: string | null
  asset_count: number
  created_at?: string
  updated_at?: string
}

export interface BusinessSystemPayload {
  code: string
  name: string
  criticality: string
  department_id?: number | null
  owner?: string | null
  owner_contact?: string | null
  owner_id?: number | null
  description?: string | null
}

export interface BusinessSystemSearchParams {
  page?: number
  page_size?: number
  keyword?: string
}

/** 列表分页（keepFullResponse，供 useTable responseAdapter 解 res.data.items） */
export function fetchBusinessSystemList(params?: BusinessSystemSearchParams) {
  return request.get<any>({
    url: BS_BASE,
    params: params || {},
    keepFullResponse: true
  })
}

/** 详情 */
export function getBusinessSystem(id: string) {
  return request.get<BusinessSystemItem>({
    url: `${BS_BASE}/${id}`
  })
}

/** 新建（admin only） */
export function createBusinessSystem(data: BusinessSystemPayload) {
  return request.post<BusinessSystemItem>({
    url: BS_BASE,
    data,
    showSuccessMessage: true,
    successMessage: '新建业务系统成功'
  })
}

/** 更新（admin only） */
export function updateBusinessSystem(id: string, data: Partial<BusinessSystemPayload>) {
  return request.put<BusinessSystemItem>({
    url: `${BS_BASE}/${id}`,
    data,
    showSuccessMessage: true,
    successMessage: '更新业务系统成功'
  })
}

/** 删除（admin only） */
export function deleteBusinessSystem(id: string) {
  return request.del({
    url: `${BS_BASE}/${id}`,
    showSuccessMessage: true,
    successMessage: '删除成功'
  })
}

/** 系统下资产列表 */
export function getBusinessSystemAssets(systemId: string) {
  return request.get<any[]>({
    url: `${BS_BASE}/${systemId}/assets`
  })
}

/** 资产-业务系统 关联（admin only） */
export function linkAssetToBusinessSystem(assetId: string, systemId: string, role?: string) {
  return request.post({
    url: `${BS_BASE}/assets/${assetId}/systems`,
    data: { system_id: systemId, role: role || null },
    showSuccessMessage: true,
    successMessage: '关联成功'
  })
}

/** 资产-业务系统 解绑（admin only） */
export function unlinkAssetFromBusinessSystem(assetId: string, systemId: string) {
  return request.del({
    url: `${BS_BASE}/assets/${assetId}/systems/${systemId}`,
    showSuccessMessage: true,
    successMessage: '解除关联成功'
  })
}
