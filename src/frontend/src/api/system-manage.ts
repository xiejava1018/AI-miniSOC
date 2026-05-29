import request from '@/utils/http'
import { AppRouteRecord } from '@/types/router'
import { asyncRoutes } from '@/router/routes/asyncRoutes'
import { RoutesAlias } from '@/router/routesAlias'
import { menuDataToRouter } from '@/router/utils/menuToRouter'

type BackendListResponse<T> = Http.BaseResponse<T[]> & {
  total?: number
  current?: number
  page?: number
  pageSize?: number
  size?: number
}

const normalizePaginationParams = (params: Record<string, any>) => {
  const { current, size, page, pageSize, ...rest } = params

  return {
    ...rest,
    page: page ?? current ?? 1,
    pageSize: pageSize ?? size ?? 10
  }
}

// 后端菜单字段映射到前端路由格式
interface BackendMenuItem {
  id: number
  name: string
  title?: string
  path: string
  icon?: string
  component?: string
  sort_order?: number
  is_visible?: boolean
  parent_id?: number | null
  children?: BackendMenuItem[]
}

/**
 * 将后端菜单转换为前端路由格式
 *
 * 后端数据结构：
 * - 父菜单：path 为绝对路径（如 /system），component 为 /index/index（Layout）
 * - 子菜单：path 为相对路径（如 users），component 为实际组件路径（如 /system/user）
 * - 占位菜单：component 为 /placeholder
 */
function backendMenuToRoute(menu: BackendMenuItem): AppRouteRecord {
  const hasChildren = menu.children && menu.children.length > 0

  // 直接使用后端返回的 component（已转换为实际路径）
  const component = menu.component || (hasChildren ? RoutesAlias.Layout : '')

  return {
    name: menu.name,
    path: menu.path,
    component,
    meta: {
      title: menu.title || menu.name,
      icon: menu.icon,
      keepAlive: !hasChildren
    },
    children: hasChildren ? menu.children!.map((child) => backendMenuToRoute(child)) : undefined
  }
}

// 获取用户列表
export function fetchGetUserList(
  params: Api.SystemManage.UserSearchParams = {}
): Promise<BackendListResponse<Api.SystemManage.UserListItem>> {
  return request.get<BackendListResponse<Api.SystemManage.UserListItem>>({
    url: '/api/v1/users',
    params: normalizePaginationParams(params as Record<string, any>),
    keepFullResponse: true,
    showErrorMessage: false
  })
}

// 获取角色列表
export function fetchGetRoleList(
  params: Api.SystemManage.RoleSearchParams = {}
): Promise<BackendListResponse<Api.SystemManage.RoleListItem>> {
  return request.get<BackendListResponse<Api.SystemManage.RoleListItem>>({
    url: '/api/v1/roles',
    params: normalizePaginationParams(params as Record<string, any>),
    keepFullResponse: true,
    showErrorMessage: false
  })
}

interface MenuResponse {
  menuList: AppRouteRecord[]
}

// 获取菜单数据（后端驱动）
export async function fetchGetMenuList(): Promise<MenuResponse> {
  try {
    // 后端控制模式：请求后端菜单树
    const backendMenus = await request.get<BackendMenuItem[]>({
      url: '/api/v1/menus/tree',
      showErrorMessage: false
    })

    if (Array.isArray(backendMenus) && backendMenus.length > 0) {
      const menuList = backendMenus.map((menu) => menuDataToRouter(backendMenuToRoute(menu)))
      return { menuList }
    }
  } catch (error) {
    console.warn('[menu] 后端菜单获取失败, 降级到本地路由数据', error)
  }

  // 降级到本地 asyncRoutes
  const localMenu = asyncRoutes.map((route) => menuDataToRouter(route))
  return { menuList: localMenu }
}
