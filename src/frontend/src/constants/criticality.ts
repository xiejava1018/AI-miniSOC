/**
 * 资产关键度（criticality）四档常量（决策1，2026-08-15）
 *
 * 后端存储统一英文枚举 critical/high/medium/low（存量 'normal' 已回填 'medium'）；
 * 前端展示统一中文（严重/高/中/低）。
 * 资产表单/资产详情主要走字典 asset_criticality（数据库驱动）；
 * 本常量用于不走字典的场景（漏洞详情的资产上下文等），保证口径一致。
 */

export const CRITICALITY_LABEL: Record<string, string> = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低'
}

export const CRITICALITY_TYPE: Record<string, string> = {
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'info'
}

/** 暴露面等级中文（vulnerability 评分上下文） */
export const EXPOSURE_LABEL: Record<string, string> = {
  public: '公网',
  internal: '内网',
  isolated: '隔离'
}
