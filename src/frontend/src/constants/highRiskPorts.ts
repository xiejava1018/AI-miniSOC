/**
 * 高危端口常量库
 *
 * 与后端 `src/backend/app/services/asset_summary.py` 的 HIGH_RISK_PORTS
 * 保持一致(单资产维度上展示"开放了哪些高危端口")。
 *
 * 修改时必须同步修改后端,反之亦然。
 */

export type PortRisk = 'critical' | 'high' | 'medium' | 'low'

export interface HighRiskPortInfo {
  port: number
  risk: PortRisk
  reason: string
}

export const HIGH_RISK_PORTS: Record<number, HighRiskPortInfo> = {
  22: { port: 22, risk: 'high', reason: 'SSH 远程管理' },
  3389: { port: 3389, risk: 'high', reason: 'RDP 远程桌面' },
  23: { port: 23, risk: 'high', reason: 'Telnet 明文协议' },
  445: { port: 445, risk: 'high', reason: 'SMB 文件共享' },
  139: { port: 139, risk: 'medium', reason: 'NetBIOS 文件共享' },
  21: { port: 21, risk: 'medium', reason: 'FTP 明文传输' },
  3306: { port: 3306, risk: 'high', reason: 'MySQL 数据库' },
  1433: { port: 1433, risk: 'high', reason: 'SQL Server 数据库' },
  5432: { port: 5432, risk: 'high', reason: 'PostgreSQL 数据库' },
  27017: { port: 27017, risk: 'high', reason: 'MongoDB 数据库' },
  6379: { port: 6379, risk: 'high', reason: 'Redis 缓存' },
  2375: { port: 2375, risk: 'critical', reason: 'Docker 未授权 API' },
  9200: { port: 9200, risk: 'high', reason: 'Elasticsearch' },
  5601: { port: 5601, risk: 'high', reason: 'Kibana 控制台' }
}

/**
 * 查询某个端口是否高危,以及风险等级和原因
 *
 * @param port 端口号
 * @returns 高危信息;非高危返回 null
 */
export const getHighRiskPort = (port: number): HighRiskPortInfo | null => {
  return HIGH_RISK_PORTS[port] ?? null
}

/**
 * Element Plus Tag 的 type 映射(用于前端展示)
 */
export const RISK_TO_TAG_TYPE: Record<PortRisk, 'danger' | 'warning' | 'info' | 'success'> = {
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'info'
}
