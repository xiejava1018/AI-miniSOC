import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1'

type BackendListResponse<T> = Http.BaseResponse<T[]> & {
  total?: number
  current?: number
  page?: number
  pageSize?: number
  size?: number
}

const normalizePaginationParams = (params?: Record<string, any>) => {
  if (!params) return undefined
  const { current, size, page, pageSize, ...rest } = params

  return {
    ...rest,
    page: page ?? current ?? 1,
    pageSize: pageSize ?? size ?? 10
  }
}

// ========== 菜单管理 ==========

export const getUserMenu = (): Promise<any[]> => {
  return httpClient.get({ url: `${API_PREFIX}/menus/tree`, showErrorMessage: false })
}

export const getAllMenu = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/menus/tree`, showErrorMessage: false })
}

export const addMenu = (data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/menus`, data })
}

export const updateMenu = (id: number, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/menus/${id}`, data })
}

export const deleteMenu = (id: string | number): Promise<Http.BaseResponse<unknown>> => {
  return httpClient.del({
    url: `${API_PREFIX}/menus/${id}`,
    keepFullResponse: true
  })
}

// ========== 角色管理 ==========

export const getRoleList = (
  params?: Record<string, any>
): Promise<BackendListResponse<Api.SystemManage.RoleListItem>> => {
  return httpClient.get({
    url: `${API_PREFIX}/roles`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const addRole = (data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/roles`, data })
}

export const updateRole = (id: number, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/roles/${id}`, data })
}

export const deleteRole = (id: number): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/roles/${id}` })
}

export const getRoleMenus = (roleID: number): Promise<Http.BaseResponse<any>> => {
  return httpClient.get({
    url: `${API_PREFIX}/roles/${roleID}/menus`,
    keepFullResponse: true
  })
}

export const assignRoleMenus = (roleID: number, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/roles/${roleID}/menus`, data })
}

// ========== 用户管理 ==========

export const getUserList = (
  params: Record<string, any>
): Promise<BackendListResponse<Api.SystemManage.UserListItem>> => {
  return httpClient.get({
    url: `${API_PREFIX}/users`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const addUser = (data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/users`, data })
}

export const updateUser = (id: number, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/users/${id}`, data })
}

export const deleteUser = (id: number): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/users/${id}` })
}

// ========== 部门管理 ==========

export const getDepartmentList = (
  params?: Record<string, any>
): Promise<BackendListResponse<Api.SystemDepartment.DepartmentItem>> => {
  return httpClient.get({
    url: `${API_PREFIX}/departments`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const getDepartmentTree = (): Promise<Api.SystemDepartment.DepartmentItem[]> => {
  return httpClient.get({ url: `${API_PREFIX}/departments/tree` })
}

export const addDepartment = (data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/departments`, data, keepFullResponse: true })
}

export const updateDepartment = (data: any): Promise<any> => {
  const id = data.id
  const payload = { ...data }
  delete payload.id
  return httpClient.put({ url: `${API_PREFIX}/departments/${id}`, data: payload, keepFullResponse: true })
}

export const deleteDepartment = (id: number): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/departments/${id}`, keepFullResponse: true })
}

// ========== 菜单元素权限 (后端暂不支持, 保留接口占位) ==========

export const getAuthList = (menuID: number): Promise<any> => {
  console.warn('[API] 菜单元素权限接口后端暂不支持')
  return Promise.resolve([])
}

export const addAuth = (data: any): Promise<any> => {
  console.warn('[API] 菜单元素权限接口后端暂不支持')
  return Promise.resolve({ code: 200, msg: 'success', data: null } as any)
}

export const updateAuth = (data: any): Promise<any> => {
  console.warn('[API] 菜单元素权限接口后端暂不支持')
  return Promise.resolve({ code: 200, msg: 'success', data: null } as any)
}

export const deleteAuth = (id: number): Promise<any> => {
  console.warn('[API] 菜单元素权限接口后端暂不支持')
  return Promise.resolve({ code: 200, msg: 'success', data: null } as any)
}

// ========== 登录日志 ==========

export const getLoginLogList = (params?: any): Promise<any> => {
  console.warn('[API] 登录日志接口后端暂不支持')
  return Promise.resolve({ code: 200, msg: 'success', data: { total: 0, items: [] } } as any)
}

// ========== 兼容别名 ==========

/** @deprecated 请使用 getRoleMenus */
export const getAllMenuByRole = getRoleMenus

/**
 * 保存角色菜单权限（兼容旧格式）
 * 将前端传来的 { role_id, menu_data } 转换为后端需要的 { menu_ids, menu_permissions }
 */
export const saveRolePermission = (data: any): Promise<any> => {
  const roleId = data.role_id
  const menuData = typeof data.menu_data === 'string' ? JSON.parse(data.menu_data) : data.menu_data

  const extractIds = (menus: any[]): number[] => {
    const ids: number[] = []
    for (const menu of menus) {
      if (menu.hasPermission && menu.id && !isNaN(Number(menu.id))) {
        ids.push(Number(menu.id))
      }
      if (menu.children && menu.children.length > 0) {
        ids.push(...extractIds(menu.children))
      }
    }
    return [...new Set(ids)]
  }

  const extractPermissions = (menus: any[]): any[] => {
    const perms: any[] = []
    for (const menu of menus) {
      if (menu.id && !isNaN(Number(menu.id)) && menu.meta?.authList && menu.meta.authList.length > 0) {
        const granted = menu.meta.authList
          .filter((a: any) => a.hasPermission)
          .map((a: any) => a.authMark)
        if (granted.length > 0) {
          perms.push({ menu_id: Number(menu.id), permissions: granted })
        }
      }
      if (menu.children && menu.children.length > 0) {
        perms.push(...extractPermissions(menu.children))
      }
    }
    return perms
  }

  const menuList = Array.isArray(menuData) ? menuData : []
  const menuIds = extractIds(menuList)
  const menuPermissions = extractPermissions(menuList)
  return assignRoleMenus(roleId, { menu_ids: menuIds, menu_permissions: menuPermissions })
}
