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
  AssetCompliance = '/asset/compliance/index', // 合规基线（P3/F3.3）
  AssetReconciliation = '/asset/reconciliation/index', // 资产稽核（P3/F1.3）
  AssetDataHealth = '/asset/data-health/index', // 数据健康：源健康/死信/稽核三层（P3/F1.3）
  SecurityReports = '/reports/list/index', // 安全报告列表/详情（P3/F2.2）
  AssetImpactAnalysis = '/asset/impact-analysis/index', // 变更影响分析（P3/F3.1）
  Incidents = '/incidents/list', // 事件管理
  Alerts = '/alert/list/index', // 告警管理
  AlertGovernance = '/alert/governance/index', // 告警治理
  Vulnerabilities = '/vulnerability/list/index', // 脆弱性管理-列表（T10 点亮）
  VulnerabilityOverview = '/vulnerability/overview/index', // 脆弱性管理-概览（T10 点亮）
  BrowsingEvent = '/browsing/event/index', // 上网行为异常事件
  BrowsingBlacklist = '/browsing/blacklist/index', // 上网行为黑名单
  BrowsingConfig = '/browsing/config/index', // 上网行为规则配置
  BrowsingLogs = '/browsing/logs/index', // 上网行为日志
  BrowsingStatistics = '/browsing/statistics/index', // 行为统计概览
  BrowsingProfile = '/browsing/profile/index', // 行为画像
  BrowsingBaseline = '/browsing/baseline/index', // 行为基线查看
  // P3 资产扫描控制面（final.md §6.4 / 原型 2026-08-26-control-plane-prototype）
  AssetScan = '/scan/index',                    // 扫描器/任务/目标/发现/健康总入口
  AssetScanners = '/scan/scanners/index',       // 扫描器列表 + 详情
  AssetScanTasks = '/scan/tasks/index',          // 扫描任务列表
  AssetScanFindings = '/scan/findings/index',    // 发现清单 + 纳管/忽略
  AssetScanTargets = '/scan/targets/index',      // 扫描目标管理
  Placeholder = '/placeholder' // 占位页面
  // 已精简：示例与演示页面别名已移除
}
