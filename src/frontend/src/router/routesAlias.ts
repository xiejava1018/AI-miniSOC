/**
 * 路由别名，方便快速找到页面，同时可以用作路由跳转
 */

/** 路由别名 */
export enum RoutesAlias {
  Layout = '/index/index', // 布局容器
  Login = '/auth/login', // 登录
  ForgetPassword = '/auth/forget-password', // 忘记密码
  Exception403 = '/exception/403', // 403
  Exception404 = '/exception/404', // 404
  Exception500 = '/exception/500', // 500
  Dashboard = '/dashboard/console', // 工作台
  User = '/system/user', // 账户
  Role = '/system/role', // 角色
  UserCenter = '/system/user-center', // 用户中心
  Menu = '/system/menu', // 菜单
  Department = '/system/department', // 部门
  AuditLog = '/system/audit-log/index', // 审计日志
  Dict = '/system/dict', // 字典管理
  SystemConfig = '/system/config', // 系统配置
  Assets = '/asset/list/index', // 资产管理
  AssetOverview = '/asset/overview/index', // 资产概览
  AssetDetail = '/asset/detail/index', // 资产详情
  Incidents = '/placeholder', // 事件管理（占位）
  Alerts = '/alert/list/index', // 告警管理
  Vulnerabilities = '/placeholder', // 脆弱性管理（占位）
  Placeholder = '/placeholder' // 占位页面
  // 已精简：示例与演示页面别名已移除
}
