import request from '@/utils/http'

const AUDIT_LOG_BASE = '/api/v1/audit-logs'

/** 获取审计日志列表（分页）
 *
 * useTable 内部会向 searchParams 注入 current/size 分页键，
 * 但后端接口使用 page/page_size 字段命名，
 * 所以这里从原始搜索参数中只提取查询条件字段，分页参数由调用方通过 paginationKey 配置
 */
export function getAuditLogList(params?: Api.AuditLog.AuditLogSearchParams) {
  return request.get({
    url: AUDIT_LOG_BASE,
    params: {
      page: (params as any)?.current ?? (params as any)?.page ?? 1,
      page_size: (params as any)?.size ?? (params as any)?.page_size ?? 20,
      user_id: (params as any)?.user_id,
      username: (params as any)?.username,
      action: (params as any)?.action,
      resource_type: (params as any)?.resource_type,
      status: (params as any)?.status,
      start_date: (params as any)?.start_date,
      end_date: (params as any)?.end_date,
    },
    keepFullResponse: true,
  })
}

/** 获取审计日志详情 */
export function getAuditLogDetail(id: number) {
  return request.get<Api.AuditLog.AuditLogItem>({
    url: `${AUDIT_LOG_BASE}/${id}`,
  })
}
