/**
 * namespace: Api
 *
 * 所有接口相关类型定义
 * 在.vue文件使用会报错，需要在 eslint.config.mjs 中配置 globals: { Api: 'readonly' }
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

  /** 部门管理 */
  namespace SystemDepartment {
    interface DepartmentItem {
      id: number
      parent_id?: number | null
      name: string
      status: number // 1 启用 / 2 禁用（后端定义）
      sort?: number
      user_count?: number
      created_at?: number
      updated_at?: number
      children?: DepartmentItem[]
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
      parent_id?: number | null
      name: string
      status: number
      sort?: number
    }
  }
}
