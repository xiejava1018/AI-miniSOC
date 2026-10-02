import request from '@/utils/http'

const BS_BASE = '/api/v1/business-systems'

export interface BusinessSystemItem {
  id: string
  code: string
  name: string
  criticality: string
  // === 治本方案：三维度重要性（2026-09-14，后端 business_systems 实回字段） ===
  business_impact: 'core' | 'important' | 'normal' | 'auxiliary' | 'ignorable' | string
  data_sensitivity: 'extreme' | 'high' | 'medium' | 'low' | 'negligible' | string
  protection_level: 'level_5' | 'level_4' | 'level_3' | 'level_2' | 'level_1' | string
  owner?: string | null
  owner_contact?: string | null
  owner_id?: number | null
  owner_username?: string | null
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
  criticality?: string
  // 三维度（创建/编辑必传 business_impact/data_sensitivity/protection_level）
  business_impact: 'core' | 'important' | 'normal' | 'auxiliary' | 'ignorable' | string
  data_sensitivity: 'extreme' | 'high' | 'medium' | 'low' | 'negligible' | string
  protection_level: 'level_5' | 'level_4' | 'level_3' | 'level_2' | 'level_1' | string
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

/** 资产-业务系统 关联（admin only）
 * 注意：不弹 showSuccessMessage——资产表单会批量 link/unlink 多个系统，
 * N 次“关联成功”提示会刷屏；由调用方统一提示。
 */
export function linkAssetToBusinessSystem(assetId: string, systemId: string, role?: string) {
  return request.post({
    url: `${BS_BASE}/assets/${assetId}/systems`,
    data: { system_id: systemId, role: role || null }
  })
}

/** 资产-业务系统 解绑（admin only）。同 link：不弹提示，由调用方统一处理。 */
export function unlinkAssetFromBusinessSystem(assetId: string, systemId: string) {
  return request.del({
    url: `${BS_BASE}/assets/${assetId}/systems/${systemId}`
  })
}
