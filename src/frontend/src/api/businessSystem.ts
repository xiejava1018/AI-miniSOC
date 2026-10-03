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
  // === 定级备案 S4 Phase 0（设计 §4.2 · 2026-10-03）===
  suggested_protection_level?: string | null
  suggestion_basis?: Record<string, any> | null
  rating_status?: 'unrated' | 'suggested' | 'confirmed' | string
  rating_confirmed_by?: string | null
  rating_confirmed_at?: string | null
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

/** 绑定覆盖率 KPI（设计 §7 T7）*/
export interface CoverageKpi {
  total_assets: number
  linked_assets: number
  coverage_rate: number
  systems_count: number
  unrated: number
  suggested_pending: number
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

/** 删除（admin only；D9 防护：有关联资产须 force=true） */
export function deleteBusinessSystem(id: string, force = false) {
  return request.del({
    url: `${BS_BASE}/${id}`,
    params: force ? { force: true } : undefined,
    showSuccessMessage: true,
    successMessage: '删除成功'
  })
}

/** 定级建议引擎（OH-4.4a · S4 红线：只产出建议，采纳走 updateBusinessSystem） */
export function suggestProtectionLevel(systemId: string) {
  return request.post<BusinessSystemItem>({
    url: `${BS_BASE}/${systemId}/suggest-protection-level`
  })
}

/** 绑定覆盖率 KPI（北极星 H1 度量） */
export function fetchCoverageKpi() {
  return request.get<CoverageKpi>({
    url: `${BS_BASE}/coverage-kpi`
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
 * inherit（设计 §5.2 D4）：undefined=仅 inherited 资产重算（默认）；true=强制继承并置
 * inherited；false=不传播。资产新建表单路径传 true（对齐前端就高预填）。
 */
export function linkAssetToBusinessSystem(
  assetId: string,
  systemId: string,
  role?: string,
  inherit?: boolean
) {
  return request.post({
    url: `${BS_BASE}/assets/${assetId}/systems`,
    data: { system_id: systemId, role: role || null, inherit: inherit }
  })
}

/** 只改关联的架构角色（设计 §7 T2；role 枚举校验在后端 schema） */
export function patchAssetBusinessRole(assetId: string, systemId: string, role: string | null) {
  return request.patch({
    url: `${BS_BASE}/assets/${assetId}/systems/${systemId}`,
    data: { role }
  })
}

/** 资产-业务系统 解绑（admin only）。同 link：不弹提示，由调用方统一处理。 */
export function unlinkAssetFromBusinessSystem(assetId: string, systemId: string) {
  return request.del({
    url: `${BS_BASE}/assets/${assetId}/systems/${systemId}`
  })
}
