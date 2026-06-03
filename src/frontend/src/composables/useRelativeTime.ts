/**
 * useRelativeTime - 把 ISO 时间戳格式化为相对时间字符串
 *
 * 阈值:
 * - < 1 分钟:"刚刚"
 * - < 1 小时:"X 分钟前"
 * - < 24 小时:"X 小时前"
 * - < 30 天:"X 天前"
 * - >= 30 天:"过期"(语义:数据陈旧,SOC 场景下需要重新扫描)
 * - 无效/空:返回 "-"
 *
 * 设计目的:资产详情页的"上次扫描时间"等位置,直接展示 ISO
 * 时间对运维人员不友好,需要相对时间。
 */

export interface UseRelativeTimeReturn {
  format: (input?: string | number | Date | null) => string
  isStale: (input?: string | number | Date | null, thresholdDays?: number) => boolean
}

const STALE_THRESHOLD_DAYS = 30

const toDate = (input?: string | number | Date | null): Date | null => {
  if (input === null || input === undefined || input === '') return null
  if (input instanceof Date) {
    return Number.isNaN(input.getTime()) ? null : input
  }
  const d = new Date(input)
  return Number.isNaN(d.getTime()) ? null : d
}

export const useRelativeTime = (): UseRelativeTimeReturn => {
  const format = (input?: string | number | Date | null): string => {
    const date = toDate(input)
    if (!date) return '-'

    const diffMs = Date.now() - date.getTime()
    // 未来时间(< 0)或者 NaN 一律当作 "刚刚"
    if (diffMs < 0) return '刚刚'

    const diffSec = Math.floor(diffMs / 1000)
    if (diffSec < 60) return '刚刚'

    const diffMin = Math.floor(diffSec / 60)
    if (diffMin < 60) return `${diffMin} 分钟前`

    const diffHour = Math.floor(diffMin / 60)
    if (diffHour < 24) return `${diffHour} 小时前`

    const diffDay = Math.floor(diffHour / 24)
    if (diffDay < STALE_THRESHOLD_DAYS) return `${diffDay} 天前`

    return '过期'
  }

  const isStale = (input?: string | number | Date | null, thresholdDays = STALE_THRESHOLD_DAYS): boolean => {
    const date = toDate(input)
    if (!date) return true
    const ageDays = (Date.now() - date.getTime()) / (1000 * 60 * 60 * 24)
    return ageDays > thresholdDays
  }

  return { format, isStale }
}
