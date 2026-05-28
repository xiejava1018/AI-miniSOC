# AI-miniSOC 前端UI框架/项目推荐

**文档类型:** 技术选型参考  
**生成时间:** 2026-05-28  
**来源:** GitHub开源项目搜索整理

---

## 现有技术栈

AI-miniSOC 前端当前采用以下技术栈：

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.5.30 | 前端框架 |
| TypeScript | ~5.9.3 | 类型系统 |
| Vite | 8.0.0 | 构建工具 |
| Element Plus | ^2.13.5 | UI组件库 |
| Pinia | ^3.0.4 | 状态管理 |
| Vue Router | ^4.6.4 | 路由管理 |
| Axios | ^1.13.6 | HTTP客户端 |

**筛选原则:** 优先推荐与现有技术栈兼容、可直接借鉴设计或低迁移成本的项目。

---

## 一、SOC专用仪表板 (功能设计参考)

这些项目专为安全运营中心(SOC)场景设计，页面布局、交互逻辑和数据模型与AI-miniSOC高度相关，适合作为功能设计参考。

### 1. demo-dashboard (SOC Dashboard)

| 属性 | 内容 |
|------|------|
| **GitHub** | [saikiran2026/demo-dashboard](https://github.com/saikiran2026/demo-dashboard) |
| **技术栈** | Next.js 14 + React 18 + TypeScript + Tailwind CSS |
| **亮点** | 功能最完整的SOC仪表板，含500条模拟告警、2000条日志、150个案例 |

**核心功能:**
- **实时告警管理**: Resolve/Snooze/False Positive标记、Severity分类(Critical/High/Medium/Low/Info)、高级筛选
- **案例管理**: P1-P5优先级、状态追踪(Open/In Progress/Closed/Escalated)、时间跟踪
- **日志分析**: 实时流式更新、多级过滤(Error/Warning/Info/Debug)、全文搜索、导出功能
- **分析报表**: Recharts图表、7天告警趋势、严重性分布饼图、KPI指标卡片
- **暗色主题**: 自定义dark theme

**对AI-miniSOC的借鉴价值:**
- 告警表格的Severity颜色标签和Status快速操作按钮设计
- 案例管理页面的卡片式网格布局
- 仪表板首页的KPI指标+趋势图+分布图组合
- 日志视图的实时更新和过滤交互

---

### 2. SOC-CERT Dashboard

| 属性 | 内容 |
|------|------|
| **GitHub** | [joupify/soc-cert-dashboard](https://github.com/joupify/soc-cert-dashboard) |
| **技术栈** | React 18 + KendoReact + Cohere AI API |
| **亮点** | AI集成最佳实践，企业级界面，暗/亮主题切换 |

**核心功能:**
- **AI威胁分析**: 集成Cohere API进行真实风险评分(非模拟)
- **实时告警网格**: KendoReact Grid组件，支持过滤/排序/分页
- **交互式图表**: 威胁分布和趋势可视化
- **主题切换**: Dark/Light双主题，针对SOC监控场景优化
- **企业集成**: n8n自动化告警接入、Redis数据持久化

**对AI-miniSOC的借鉴价值:**
- AI分析面板的设计：风险评分展示、处置建议排版
- 暗色主题实现方案(KendoReact自定义CSS)
- 告警详情页嵌入AI分析结果的交互模式
- 企业级错误处理和fallback机制

**在线演示:** [https://soc-cert-dashboard.vercel.app/](https://soc-cert-dashboard.vercel.app/)

---

### 3. AI_SOC

| 属性 | 内容 |
|------|------|
| **GitHub** | [zhadyz/AI_SOC](https://github.com/zhadyz/AI_SOC) |
| **亮点** | AI增强SOC，网络拓扑环境建模，CVE防御控制 |

**借鉴价值:**
- AI+SOC的架构设计思路
- 网络拓扑可视化方案
- 漏洞管理与防御控制的联动设计

---

## 二、Vue3技术栈匹配 (可直接复用)

这些项目与AI-miniSOC当前技术栈完全一致或高度兼容，可直接参考代码或作为重构基础。

### 1. art-design-pro (最推荐)

| 属性 | 内容 |
|------|------|
| **GitHub** | [Daymychen/art-design-pro](https://github.com/Daymychen/art-design-pro) |
| **技术栈** | Vue 3 + Vite + TypeScript + Element Plus |
| **stars** | ~2k |

**核心特性:**
- **100%技术栈匹配**: Vue3 + Vite + TS + Element Plus，与AI-miniSOC完全一致
- **30+页面**: 预置丰富的admin页面模板
- **RBAC权限系统**: 角色权限管理、动态路由、菜单权限控制
- **暗色模式**: 内置一键切换暗色主题
- **8种主题**: 多种配色方案可选
- **i18n国际化**: 多语言支持
- **表单/表格生成器**: 快速构建CRUD页面

**对AI-miniSOC的价值:**
- 可作为前端重构的直接基础框架
- RBAC系统可与现有后端权限API对接
- 暗色主题实现可直接参考
- 表单生成器适合快速构建资产管理、用户管理等CRUD页面

---

### 2. vue-typescript-admin-template

| 属性 | 内容 |
|------|------|
| **GitHub** | [Armour/vue-typescript-admin-template](https://github.com/Armour/vue-typescript-admin-template) |
| **技术栈** | Vue + TypeScript + Element UI |
| **stars** | ~5k |

**核心特性:**
- 生产就绪的Admin方案
- JWT鉴权、权限管理、动态路由
- 代码生成器、表单生成器
- 可配置的导入导出
- 多点登录拦截

**注意:** 基于Vue 2 + Element UI，迁移到Vue3 + Element Plus需要一定工作量。

---

### 3. vuestic-admin

| 属性 | 内容 |
|------|------|
| **GitHub** | [epicmaxco/vuestic-admin](https://github.com/epicmaxco/vuestic-admin) |
| **技术栈** | Vue 3 + Vite + Pinia + Tailwind CSS |
| **stars** | ~3k |

**核心特性:**
- Vue3生态，美观现代的UI设计
- 响应式布局，移动端适配
- 丰富的组件库(Vuestic UI)

**注意:** 使用Vuestic UI而非Element Plus，组件风格与现有项目差异较大。

---

## 三、SOC架构/工作流参考

### 1. soc-toolkit

| 属性 | 内容 |
|------|------|
| **GitHub** | [phrp720/soc-toolkit](https://github.com/phrp720/soc-toolkit) |
| **说明** | 开源SOC工具集，Wazuh + Shuffle(SOAR) + TheHive(案件管理)的自动化工作流 |

**借鉴价值:**
- 开源SOC的完整架构设计
- Wazuh与其他安全工具的集成方案
- SOAR自动化工作流设计

---

### 2. Microsoft SOC Toolkit

| 属性 | 内容 |
|------|------|
| **GitHub** | [microsoft/SOC](https://github.com/microsoft/SOC) |
| **说明** | 微软学生SOC培训工具包，3小时交互式训练 |

**借鉴价值:**
- SOC培训材料和最佳实践
- 威胁检测和响应的标准流程
- 适合作为团队培训参考

---

### 3. OpenSOC

| 属性 | 内容 |
|------|------|
| **官网** | [https://opensoc.github.io/](https://opensoc.github.io/) |
| **说明** | Apache开源的可扩展安全分析平台 |

**借鉴价值:**
- 大规模安全数据分析架构
- 实时流式处理设计
- 可扩展的检测规则引擎

---

## 四、推荐方案

### 方案A: 最小改动 (推荐)

**策略:** 保持现有Vue3 + Element Plus架构，借鉴专用SOC项目的页面设计和交互逻辑。

**具体行动:**

1. **仪表板首页优化** (参考 demo-dashboard)
   - 增加KPI指标卡片：活跃告警数、待处理案例、系统状态、日志事件数
   - 增加告警趋势图(7天/30天)
   - 增加严重性分布饼图/环形图
   - 最近活动时间线

2. **告警管理页面增强** (参考 demo-dashboard + soc-cert-dashboard)
   - Severity颜色标签：Critical(红)/High(橙)/Medium(黄)/Low(蓝)/Info(灰)
   - Status快速操作：Resolve/Snooze/Mark False Positive
   - 告警详情抽屉面板：基本信息 + AI分析结果 + 关联日志
   - 高级筛选栏：按Severity/Status/Source/Time Range筛选

3. **暗色主题实现** (参考 art-design-pro + soc-cert-dashboard)
   - Element Plus已原生支持暗色主题
   - 参考实现顶部导航栏的一键主题切换
   - 针对SOC监控场景优化暗色配色(降低对比度，保护视力)

4. **AI分析面板设计** (参考 soc-cert-dashboard)
   - 告警详情页嵌入AI分析卡片
   - 风险评分可视化(进度条/仪表盘)
   - 处置建议列表展示
   - 原始JSON输出折叠面板(供专家验证)

---

### 方案B: 基于 art-design-pro 重构

**策略:** 如当前前端代码结构较混乱或需要统一设计规范，可直接基于 art-design-pro 重构。

**优势:**
- 技术栈100%匹配，零迁移成本
- 已内置RBAC、暗色模式、i18n等基础能力
- 表单/表格生成器可快速构建CRUD页面
- 30+页面模板可直接复用或改造

**工作量评估:**
- 保留现有后端API接口不变
- 迁移现有页面逻辑到新的组件结构
- 约1-2周可完成基础框架迁移

---

## 五、快速参考对比表

| 项目 | 技术栈 | SOC专用 | 暗色主题 | AI集成 | 可借鉴度 |
|------|--------|---------|---------|--------|---------|
| demo-dashboard | Next.js/React | 是 | 是 | 否 | 高(功能设计) |
| soc-cert-dashboard | React/KendoReact | 是 | 是 | 是(Cohere) | 高(AI面板) |
| art-design-pro | Vue3/ElementPlus | 否 | 是 | 否 | 高(技术栈匹配) |
| vue-typescript-admin-template | Vue2/ElementUI | 否 | 否 | 否 | 中(权限系统) |
| AI_SOC | 未明确 | 是 | 未明确 | 是 | 中(架构) |

---

## 六、后续行动建议

1. **短期(本周)**:
   - 本地运行 demo-dashboard 和 soc-cert-dashboard，体验交互流程
   - 截取关键页面设计作为AI-miniSOC前端优化参考

2. **中期(本月)**:
   - 基于现有Vue3架构，实现暗色主题切换
   - 优化告警管理页面，增加Severity标签和Status快速操作
   - 设计AI分析结果展示组件

3. **长期(下季度)**:
   - 评估是否基于 art-design-pro 进行前端重构
   - 统一前端设计规范和组件库
   - 完善响应式布局，支持移动端查看

---

*本文档基于GitHub开源项目搜索整理，项目链接和状态可能随时间变化，建议访问GitHub获取最新信息。*
