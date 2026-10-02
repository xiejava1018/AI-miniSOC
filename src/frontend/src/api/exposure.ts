/**
 * 暴露面归位 API client（S2 / OH-4.2 / OH-UI.9）

对应后端：
  GET /api/v1/exposure/lookup?wan_ip=...        外网 IP→内网反查
  GET /api/v1/exposure/rules                  全量 NAT 规则（暴露面分析页数据源）
  GET /api/v1/exposure/assets/{id}/mapping     资产对外暴露面映射

envelope：{code, msg, data}（HTTP 200 + 业务码），
本文件统一 keepFullResponse=true 由调用方取 .data。
 */
import request from '@/utils/http'

const EXPOSURE_BASE = '/api/v1/exposure'

/** 反查：wan_ip → 内网资产（含定位率口径：located/unlocated） */
export function exposureLookup(params: { wan_ip: string; enabled_only?: boolean }) {
  return request.get<any>({
    url: `${EXPOSURE_BASE}/lookup`,
    params: {
      wan_ip: params.wan_ip,
      enabled_only: params.enabled_only ?? true
    },
    keepFullResponse: true
  })
}

/** 全量 NAT 规则（支持按 internal_ip 过滤；汇总 wan_ip / exposed_asset / unlocated 计数） */
export function exposureRules(params?: {
  internal_ip?: string
  enabled_only?: boolean
  limit?: number
}) {
  return request.get<any>({
    url: `${EXPOSURE_BASE}/rules`,
    params: {
      internal_ip: params?.internal_ip,
      enabled_only: params?.enabled_only ?? true,
      limit: params?.limit ?? 200
    },
    keepFullResponse: true
  })
}

/** 资产对外暴露面映射（"这台资产哪些端口暴露在公网"） */
export function assetExposureMapping(assetId: string, params?: { enabled_only?: boolean }) {
  return request.get<any>({
    url: `${EXPOSURE_BASE}/assets/${assetId}/mapping`,
    params: {
      enabled_only: params?.enabled_only ?? true
    },
    keepFullResponse: true
  })
}
