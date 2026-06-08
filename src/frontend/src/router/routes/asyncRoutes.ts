import { RoutesAlias } from '../routesAlias'
import { AppRouteRecord } from '@/types/router'

/**
 * 精简后的异步路由
 * 仅保留：仪表盘、系统管理、异常页面、外链示例
 * 其余示例页面（article/change/examples/result/safeguard/template/widgets）已移除
 */
export const asyncRoutes: AppRouteRecord[] = [
  {
    name: 'Dashboard',
    path: '/dashboard',
    component: RoutesAlias.Layout,
    meta: {
      title: '仪表盘',
      icon: '&#xe721;',
      roles: ['R_SUPER', 'R_ADMIN']
    },
    children: [
      {
        path: 'console',
        name: 'Console',
        component: RoutesAlias.Dashboard,
        meta: {
          title: '工作台',
          keepAlive: false,
          fixedTab: true
        }
      }
    ]
  },

  {
    path: '/system',
    name: 'System',
    component: RoutesAlias.Layout,
    meta: {
      title: '系统管理',
      icon: '&#xe7b9;',
      roles: ['R_SUPER', 'R_ADMIN']
    },
    children: [
      {
        path: 'user',
        name: 'User',
        component: RoutesAlias.User,
        meta: {
          title: '用户管理',
          keepAlive: true,
          roles: ['R_SUPER', 'R_ADMIN']
        }
      },
      {
        path: 'role',
        name: 'Role',
        component: RoutesAlias.Role,
        meta: {
          title: '角色管理',
          keepAlive: true,
          roles: ['R_SUPER']
        }
      },
      {
        path: 'user-center',
        name: 'UserCenter',
        component: RoutesAlias.UserCenter,
        meta: {
          title: '个人中心',
          isHide: true,
          keepAlive: true,
          isHideTab: true
        }
      },
      {
        path: 'menu',
        name: 'Menus',
        component: RoutesAlias.Menu,
        meta: {
          title: '菜单管理',
          keepAlive: true,
          roles: ['R_SUPER'],
          authList: [
            { title: '新增', authMark: 'add' },
            { title: '编辑', authMark: 'edit' },
            { title: '删除', authMark: 'delete' }
          ]
        }
      },
      {
        path: 'dict',
        name: 'Dict',
        component: RoutesAlias.Dict,
        meta: {
          title: '字典管理',
          keepAlive: true,
          roles: ['R_SUPER', 'R_ADMIN']
        }
      },
      {
        path: 'config',
        name: 'SystemConfig',
        component: RoutesAlias.SystemConfig,
        meta: {
          title: '系统配置',
          keepAlive: true,
          roles: ['R_SUPER', 'R_ADMIN'],
          authList: [
            { title: '新增', authMark: 'add' },
            { title: '编辑', authMark: 'edit' },
            { title: '删除', authMark: 'delete' }
          ]
        }
      }
    ]
  },

  {
    path: '/assets',
    name: 'Asset',
    component: RoutesAlias.Layout,
    meta: {
      title: '资产管理',
      icon: '&#xe6ca;',
      roles: ['R_SUPER', 'R_ADMIN']
    },
    children: [
      {
        // 资产概览(SOC 风险全貌),放在第一位作为高频入口
        path: 'overview',
        name: 'AssetOverview',
        component: RoutesAlias.AssetOverview,
        meta: {
          title: '资产概览',
          keepAlive: true,
          roles: ['R_SUPER', 'R_ADMIN']
        }
      },
      {
        path: 'list',
        name: 'AssetList',
        component: RoutesAlias.Assets,
        meta: {
          title: '资产列表',
          keepAlive: true,
          roles: ['R_SUPER', 'R_ADMIN'],
          authList: [
            { title: '新增', authMark: 'add' },
            { title: '编辑', authMark: 'edit' },
            { title: '删除', authMark: 'delete' }
          ]
        }
      },
      {
        path: 'detail/:id',
        name: 'AssetDetail',
        component: RoutesAlias.AssetDetail,
        meta: {
          title: '资产详情',
          isHide: true,
          keepAlive: false,
          isHideTab: true
        }
      }
    ]
  },

  {
    path: '/alert',
    name: 'Alert',
    component: RoutesAlias.Layout,
    meta: {
      title: '告警管理',
      icon: '&#xe63a;',
      roles: ['R_SUPER', 'R_ADMIN']
    },
    children: [
      {
        path: 'list',
        name: 'AlertList',
        component: RoutesAlias.Alerts,
        meta: {
          title: '告警列表',
          keepAlive: true,
          roles: ['R_SUPER', 'R_ADMIN']
        }
      }
    ]
  },

  {
    path: '/exception',
    name: 'Exception',
    component: RoutesAlias.Layout,
    meta: {
      title: '异常页面',
      icon: '&#xe820;'
    },
    children: [
      {
        path: '403',
        name: '403',
        component: RoutesAlias.Exception403,
        meta: { title: '403', keepAlive: true, isFullPage: true }
      },
      {
        path: '404',
        name: '404',
        component: RoutesAlias.Exception404,
        meta: { title: '404', keepAlive: true, isFullPage: true }
      },
      {
        path: '500',
        name: '500',
        component: RoutesAlias.Exception500,
        meta: { title: '500', keepAlive: true, isFullPage: true }
      }
    ]
  }
]
