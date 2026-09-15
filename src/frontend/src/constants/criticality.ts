/**
 * 资产重要性 · 三维度常量（治本方案 · 2026-09-14）
 *
 * 第一性原理（ISO 27005 / NIST SP 800-30 / 等保 2.0）：
 *   资产重要性拆为 3 个独立维度：
 *     1. business_impact    业务影响（BIA）5 档：核心/重要/一般/辅助/可忽略
 *                          → 驱动 SLA / 推送优先级 / 应急响应
 *     2. data_sensitivity   数据敏感度（CIA）5 档：极高/高/中/低/可公开
 *                          → 驱动风险评分加权
 *     3. protection_level   等保等级 5 档：等保五级 ~ 等保一级
 *                          → 合规报告 / 等保检查
 *
 * 旧 criticality 字段保留为 deprecated read-only alias（6 个月过渡期），
 * 兼容垫片从 data_sensitivity 派生。
 *
 * 资产表单/详情主要走字典 asset_business_impact / asset_data_sensitivity /
 * protection_level（数据库驱动）；本常量用于不走字典的场景（详情页悬浮提示等）。
 */

// ============================================================================
// 业务影响（BIA）5 档
// ============================================================================

export const BUSINESS_IMPACT_LABEL: Record<string, string> = {
  core: '核心业务',
  important: '重要业务',
  normal: '一般业务',
  auxiliary: '辅助支撑',
  ignorable: '可忽略'
}

export const BUSINESS_IMPACT_TYPE: Record<string, string> = {
  core: 'danger',
  important: 'danger',
  normal: 'warning',
  auxiliary: 'info',
  ignorable: 'info'
}

// 排序（重要→次要）
export const BUSINESS_IMPACT_ORDER = ['core', 'important', 'normal', 'auxiliary', 'ignorable'] as const

// ============================================================================
// 数据敏感度（CIA）5 档
// ============================================================================

export const DATA_SENSITIVITY_LABEL: Record<string, string> = {
  extreme: '极高',
  high: '高',
  medium: '中',
  low: '低',
  negligible: '可公开'
}

export const DATA_SENSITIVITY_TYPE: Record<string, string> = {
  extreme: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'info',
  negligible: 'info'
}

export const DATA_SENSITIVITY_ORDER = ['extreme', 'high', 'medium', 'low', 'negligible'] as const

// ============================================================================
// 等保等级 5 档
// ============================================================================

export const PROTECTION_LEVEL_LABEL: Record<string, string> = {
  level_5: '等保五级',
  level_4: '等保四级',
  level_3: '等保三级',
  level_2: '等保二级',
  level_1: '等保一级'
}

export const PROTECTION_LEVEL_TYPE: Record<string, string> = {
  level_5: 'danger',
  level_4: 'danger',
  level_3: 'warning',
  level_2: 'info',
  level_1: 'info'
}

export const PROTECTION_LEVEL_ORDER = ['level_5', 'level_4', 'level_3', 'level_2', 'level_1'] as const

// ============================================================================
// criticality（DEPRECATED 兼容垫片，6 个月过渡期）
// ============================================================================
// 反向映射：5 档 data_sensitivity → 4 档 criticality
// 与后端 app.core.criticality.legacy_criticality_from_data_sensitivity 对齐
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

export const DATA_SENSITIVITY_TO_CRITICALITY: Record<string, string> = {
  extreme: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
  negligible: 'low'  // 5 档低 → 4 档低（旧代码无 negligible 概念）
}

/** 从 5 档 CIA 反推 4 档 criticality（兼容垫片） */
export function legacyCriticalityFromDataSensitivity(ds: string | null | undefined): string {
  if (!ds) return 'medium'
  return DATA_SENSITIVITY_TO_CRITICALITY[ds] || 'medium'
}

// ============================================================================
// 暴露面等级（保留）
// ============================================================================

export const EXPOSURE_LABEL: Record<string, string> = {
  public: '公网',
  internal: '内网',
  isolated: '隔离'
}
