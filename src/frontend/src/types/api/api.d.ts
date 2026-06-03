/**
 * API 接口类型定义模块
 *
 * 提供所有后端接口的类型定义
 *
 * ## 主要功能
 *
 * - 通用类型（分页参数、响应结构等）
 * - 认证类型（登录、用户信息等）
 * - 系统管理类型（用户、角色等）
 * - 全局命名空间声明
 *
 * ## 使用场景
 *
 * - API 请求参数类型约束
 * - API 响应数据类型定义
 * - 接口文档类型同步
 *
 * ## 注意事项
 *
 * - 在 .vue 文件使用需要在 eslint.config.mjs 中配置 globals: { Api: 'readonly' }
 * - 使用全局命名空间，无需导入即可使用
 *
 * ## 使用方式
 *
 * ```typescript
 * const params: Api.Auth.LoginParams = { userName: 'admin', password: '123456' }
 * const response: Api.Auth.UserInfo = await fetchUserInfo()
 * ```
 *
 * @module types/api/api
 * @author Art Design Pro Team
 */

declare namespace Api {
  /** 通用类型 */
  namespace Common {
    /** 分页参数 */
    interface PaginationParams {
      /** 当前页码 */
      current: number
      /** 每页条数 */
      size: number
      /** 总条数 */
      total: number
    }

    /** 通用搜索参数 */
    type CommonSearchParams = Pick<PaginationParams, 'current' | 'size'>

    /** 分页响应基础结构 */
    interface PaginatedResponse<T = any> {
      records: T[]
      current?: number
      size?: number
      total: number
    }

    /** 启用状态 */
    type EnableStatus = '1' | '2'
  }

  /** 认证类型 */
  namespace Auth {
    /** 登录参数 */
    interface LoginParams {
      username: string
      password: string
      captcha_key?: string
      captcha_code?: string
    }

    interface CaptchaResponse {
      captcha_key: string
      captcha_image: string
    }

    /** 登录响应 */
    interface LoginResponse {
      access_token: string
      refresh_token: string
      token_type: string
      expires_in: number
      user: UserInfo
    }

    /** 用户信息 */
    interface UserInfo {
      id?: number | string
      userId?: number
      userName?: string
      username?: string
      name?: string
      account?: string
      nickName?: string
      email?: string
      phone?: string
      gender?: number
      avatar?: string
      roles?: string[]
      buttons?: string[]
      [key: string]: any
    }

  }

  /** 系统管理类型 */
  namespace SystemManage {
    /** 用户列表 */
    type UserList = Api.Common.PaginatedResponse<UserListItem>

    /** 用户列表项（系统管理接口返回结构） */
    interface UserListItem {
      id: number
      username?: string
      name: string
      account?: string
      phone?: string
      email?: string | null
      gender?: number | null
      status?: number
      avatar?: string | null
      role_id?: number | null
      role_name?: string | null
      role_desc?: string | null
      department_id?: number | null
      department_name?: string | null
      created_at?: number | string
      updated_at?: number | string
      [key: string]: any
    }

    /** 用户搜索参数 */
    type UserSearchParams = Partial<
      Pick<
        UserListItem,
        'id' | 'username' | 'name' | 'phone' | 'gender' | 'status' | 'role_id' | 'department_id'
      >
    > & {
      page?: number
      pageSize?: number
      current?: number
      size?: number
    }

    /** 角色列表 */
    type RoleList = Api.Common.PaginatedResponse<RoleListItem>

    /** 角色列表项（与系统管理接口对齐） */
    interface RoleListItem {
      id: number
      name: string
      desc?: string
      status?: number
      created_at?: number | string
      updated_at?: number | string
      users?: any[]
      [key: string]: any
    }

    /** 角色搜索参数 */
    type RoleSearchParams = Partial<Pick<RoleListItem, 'id' | 'name' | 'status'>> & {
      page?: number
      pageSize?: number
      current?: number
      size?: number
    }
  }

  /** 资产管理 */
  namespace Asset {
    /** 资产列表项 */
    interface AssetListItem {
      id: string
      name?: string
      network_segment?: string
      network_zone?: string
      asset_ip: string
      asset_type?: string
      criticality?: string
      owner?: string
      business_unit?: string
      asset_description?: string
      mac_address?: string
      wazuh_agent_id?: string
      asset_status?: string
      os_name?: string
      os_version?: string
      hardware_info?: Record<string, any>
      data_source?: string
      last_synced_at?: string
      parent_id?: string
      status_updated_at?: string
      created_at?: string
      updated_at?: string
    }

    /** 资产搜索参数 */
    interface AssetSearchParams {
      page?: number
      pageSize?: number
      asset_ip?: string
      name?: string
      asset_type?: string
      criticality?: string
      asset_status?: string
      network_zone?: string
      data_source?: string
    }

    /** 资产创建/编辑表单 */
    interface AssetPayload {
      id?: string
      name?: string
      network_segment?: string
      network_zone?: string
      asset_ip?: string
      asset_type?: string
      criticality?: string
      owner?: string
      business_unit?: string
      asset_description?: string
      mac_address?: string
      wazuh_agent_id?: string
      asset_status?: string
    }

    /** 端口列表项 */
    interface AssetPortItem {
      id: string
      asset_id?: string
      asset_ip: string
      port: number
      protocol: string
      state: string
      service?: string
      version?: string
      service_banner?: string
      vulnerability?: string
      scan_time?: string
      last_seen?: string
      created_at?: string
    }

    /** 标签列表项 */
    interface AssetTagItem {
      id: string
      asset_id: string
      tag_key: string
      tag_value: string
      created_at?: string
    }

    /** 资产安全摘要(详情页 v2 §7.1) */
    interface AssetSummary {
      asset_id: string
      /** 在线状态: online / offline / unknown */
      online_status: 'online' | 'offline' | 'unknown'
      /** 近 24h 告警总数 */
      alert_24h: number
      /** 近 24h 高危告警数(Wazuh level >= 12) */
      alert_critical_24h: number
      /** 未关闭事件数(status != closed) */
      open_incidents: number
      /** 漏洞统计(Phase 2 接入) */
      vuln_critical: number
      vuln_high: number
      vuln_total: number
      /** 开放端口统计 */
      open_ports: number
      high_risk_ports: number
      /** 应用数量(Wazuh packages, Phase 2 接入) */
      applications: number
      /** SCA 基线合规率(0-1, Phase 2 接入) */
      sca_pass_rate: number | null
      sca_total: number
      sca_failed: number
      /** 最近一次扫描时间(ISO) */
      last_port_scan: string | null
      last_vuln_scan: string | null
      last_sca_scan: string | null
      /** 数据敏感等级 */
      data_classification: string
      /** 负责人信息 */
      owner: string | null
      owner_contact: string | null
      /** 标签 */
      tags: { key: string; value: string }[]
    }

    /** 资产概览 - KPI 区(概览页 §5.1) */
    interface AssetOverviewKpi {
      total_assets: number
      high_risk_assets: number
      alerts_24h: number
      open_incidents: number
    }

    /** 资产概览 - 分布图统一项 */
    interface AssetDistributionItem {
      key: string
      count: number
    }

    /** 资产概览 - 分布图 */
    interface AssetOverviewDistribution {
      by_type: AssetDistributionItem[]
      by_status: AssetDistributionItem[]
      by_criticality: AssetDistributionItem[]
    }

    /** 资产概览 - 24h 告警趋势(1h 桶) */
    interface AssetOverviewTrendPoint {
      hour: string
      total: number
      critical: number
    }

    /** 资产概览 - Top 10 高危资产(D7 评分) */
    interface AssetOverviewTopRisky {
      id: string
      ip: string
      name: string
      asset_type: string | null
      criticality: string | null
      score: number
      factors: string[]
    }

    /** 资产概览 - Top 10 告警资产 */
    interface AssetOverviewTopAlert {
      id: string | null
      ip: string
      name: string
      asset_type: string | null
      alert_24h: number
      alert_critical_24h: number
      last_alert_at: string | null
    }

    /** 资产概览 - 完整数据(概览页 + console 入口卡共用) */
    interface AssetOverview {
      kpi: AssetOverviewKpi
      distribution: AssetOverviewDistribution
      alert_trend_24h: AssetOverviewTrendPoint[]
      top_risky_assets: AssetOverviewTopRisky[]
      top_alert_assets: AssetOverviewTopAlert[]
    }
  }

  /** 部门管理 */
  namespace SystemDepartment {
    interface DepartmentItem {
      id: number
      name: string
      status: number // 1 启用 / 2 禁用（后端定义）
      sort?: number
      created_at?: number
      updated_at?: number
    }

    interface DepartmentSearchParams {
      page?: number
      page_size?: number
      pageSize?: number
      name?: string
      status?: number
    }

    interface DepartmentPayload {
      id?: number
      name: string
      status: number
      sort?: number
    }
  }

  /** 字典管理 */
  namespace SystemDict {
    interface DictItem {
      id: number
      dict_type: string
      dict_code: string
      dict_label: string
      color?: string | null
      sort_order: number
      is_active: boolean
      is_default: boolean
      remark?: string | null
      created_at?: string
      updated_at?: string
    }

    interface DictSearchParams {
      current?: number
      size?: number
      page?: number
      page_size?: number
      dict_type?: string
      search?: string
    }

    interface DictPayload {
      id?: number
      dict_type: string
      dict_code: string
      dict_label: string
      color?: string | null
      sort_order?: number
      is_active?: boolean
      is_default?: boolean
      remark?: string | null
    }
  }

  namespace SystemConfig {
    type ValueType = 'string' | 'number' | 'boolean' | 'json' | 'password'

    interface ConfigItem {
      id: number
      category: string
      key: string
      value: string | null
      value_type: ValueType
      is_encrypted: boolean
      description: string | null
      updated_by: number | null
      created_at?: string
      updated_at?: string
    }

    interface ConfigSearchParams {
      current?: number
      size?: number
      page?: number
      page_size?: number
      category?: string
      search?: string
    }

    interface ConfigPayload {
      category: string
      key: string
      value?: string | null
      value_type?: ValueType
      is_encrypted?: boolean
      description?: string | null
    }

    interface CategoryItem {
      category: string
      count: number
    }
  }

  /** 审计日志 */
  namespace AuditLog {
    interface AuditLogItem {
      id: number
      user_id?: number | null
      username: string
      action: string
      resource_type?: string | null
      resource_id?: number | null
      resource_name?: string | null
      old_values?: any
      new_values?: any
      ip_address?: string | null
      user_agent?: string | null
      session_id?: number | null
      request_id?: string | null
      status: string
      error_message?: string | null
      created_at?: string
    }

    interface AuditLogSearchParams {
      current?: number
      size?: number
      page?: number
      page_size?: number
      user_id?: number
      username?: string
      action?: string
      resource_type?: string
      status?: string
      start_date?: string
      end_date?: string
    }
  }
}
