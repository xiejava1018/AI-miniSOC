import request from '@/utils/http'

const BASE = '/api/v1/ai-assets'

export type AIAssetKind = 'model' | 'data' | 'agent' | 'tool' | 'credential' | 'compute'
export type AIAssetStatus = 'registered' | 'shadow' | 'sanctioned' | 'decommissioned'
export type AIAssetRisk = 'low' | 'medium' | 'high' | 'critical'

export interface AIAsset {
  id: string
  kind: AIAssetKind
  name: string
  provider?: string
  version?: string
  owner?: string
  business_unit?: string
  business_system_id?: string | null
  status: AIAssetStatus
  risk_level: AIAssetRisk
  details: Record<string, any>
  description?: string
  discovery_source: string
  created_at?: string
  updated_at?: string
}

export interface AIAssetDashboard {
  total: number
  by_kind: Record<string, number>
  by_status: Record<string, number>
  by_risk: Record<string, number>
  shadow_ai_count: number
  red_line?: string
}

export interface AIAssetListResp {
  total: number
  items: AIAsset[]
}

export interface AIAssetCreatePayload {
  kind: AIAssetKind
  name: string
  provider?: string
  version?: string
  owner?: string
  business_unit?: string
  business_system_id?: string | null
  status?: AIAssetStatus
  risk_level?: AIAssetRisk
  details?: Record<string, any>
  description?: string
  discovery_source?: string
}

export function listAIAssets(params?: {
  kind?: AIAssetKind
  status?: AIAssetStatus
  limit?: number
}) {
  return request.get<AIAssetListResp>({ url: BASE, params })
}

export function getAIAssetDashboard() {
  return request.get<AIAssetDashboard>({ url: `${BASE}/dashboard` })
}

export function getAIAsset(id: string) {
  return request.get<AIAsset>({ url: `${BASE}/${id}` })
}

export function createAIAsset(data: AIAssetCreatePayload) {
  return request.post<AIAsset>({
    url: BASE,
    data,
    showSuccessMessage: true,
    successMessage: '登记成功',
  })
}
