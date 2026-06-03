/**
 * 公共系统信息 API（不需鉴权）
 *
 * 数据源：后端 /api/v1/public/system-info
 * 用于浏览器 <title>、登录页、顶栏、关于弹窗等前台展示场景。
 */
import request from '@/utils/http'

const BASE = '/api/v1/public'

/** 公共系统信息响应字段（白名单） */
export interface PublicSystemInfo {
  system_name: string
  system_logo: string
  system_copyright: string
  system_description: string
  allowed_hosts: string  // 允许的主机列表，"all" 表示允许所有，否则为逗号分隔的域名列表
}

/**
 * 获取公共系统信息。
 * http 工具会自动 unwrap envelope (body.data)，调用方直接拿到字段对象。
 */
export function getPublicSystemInfo() {
  return request.get<PublicSystemInfo>({
    url: `${BASE}/system-info`,
  })
}
