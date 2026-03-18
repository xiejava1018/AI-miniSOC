# AI-miniSOC 产品定位与技术路线

**文档版本**: v1.0
**创建日期**: 2026-03-18
**最后更新**: 2026-03-18

## 📋 文档说明

本文档记录AI-miniSOC项目的核心定位、架构思路和MVP规划，作为后续开发的方向指南。

## 🎯 产品定位

### 核心定位
**低成本 + AI增强的完整SOC运营平台**

### 发展路径
- **当前阶段**: 内部SOC工具
- **未来目标**: 成熟后开源
- **最终愿景**: 个人/小团队/小企业用得起的安全运营平台

### 目标用户
1. **个人用户**: 安全研究员、独立顾问
2. **小团队**: 5-50人的公司
3. **小企业**: 预算有限、买不起商业SOC(Splunk/QRadar)的组织

### 核心价值主张
- **低成本**: 开源工具 + 简单部署
- **AI增强**: 智能化降低运营门槛
- **完整SOC**: 不只是SIEM，提供闭环运营能力

### 核心痛点
1. **Wazuh功能不全**: 作为SIEM很好，但缺少SOC的资产管理、事件工作流等能力
2. **告警看不懂**: Wazuh告警技术性强，需要AI翻译成人话

## 🏗️ 架构设计思路

### 核心原则
**"不要重新发明轮子，专注于Wazuh做不好的事"**

### SOC vs SIEM 能力分析

```
SIEM能力 (Wazuh已提供):
├── 日志收集 ✅
├── 威胁检测 ✅
├── 告警规则 ✅
└── 基础查询 ✅

SOC能力 (Wazuh缺失,需要补充):
├── 资产管理 ❌
├── 漏洞/暴露面管理 ❌
├── 事件响应工作流 ❌
├── 威胁狩猎 ❌
├── 合规报告 ❌
└── 知识库 ❌

AI增强能力 (核心卖点):
├── 智能告警解释 🤖
├── 事件根因分析 🤖
├── 自动化响应建议 🤖
└── 自然语言查询 🤖
```

### 系统架构图

```
┌─────────────────────────────────────────┐
│         AI-miniSOC Frontend             │
│           (Vue.js)                      │
│    资产 | 事件 | 告警 | AI分析           │
└──────────────┬──────────────────────────┘
               │
┌──────────────┴──────────────────────────┐
│         AI-miniSOC Backend              │
│           (FastAPI)                     │
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │资产管理  │  │事件工作流 │  │AI分析  ││
│  └──────────┘  └──────────┘  └────────┘│
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐ ┌───▼───┐ ┌────▼────┐
│ Wazuh │ │ Loki  │ │ AI模型  │
│ API   │ │ API   │ │ API服务 │
└───────┘ └───────┘ └─────────┘
```

## 🔧 技术栈

### 前端
- **框架**: Vue.js 3
- **状态管理**: Pinia
- **路由**: Vue Router
- **UI组件**: Element Plus / Ant Design Vue
- **HTTP客户端**: Axios

### 后端
- **框架**: **FastAPI** ✅
  - 自动API文档（/docs）
  - 原生异步支持
  - 类型注解
  - 性能优秀
- **数据库**: PostgreSQL
- **ORM**: SQLAlchemy 2.0 (async)
- **数据验证**: Pydantic
- **认证**: JWT

### AI能力
- **模型服务**: 开源模型API
  - 通义千问 (阿里云)
  - 智谱AI (GLM)
  - DeepSeek
  - 备选：本地Ollama
- **原因**:
  - 成本低
  - 中文友好
  - 数据隐私
  - 避免依赖OpenAI

### 基础设施
- **容器**: Docker + Docker Compose
- **反向代理**: Nginx
- **监控**: 已有Wazuh + Loki + Grafana

## 📦 服务架构

### 删除的服务（避免重复）

| 原规划 | 建议 | 理由 |
|--------|------|------|
| `alert-engine/` | **删除** | Wazuh已有告警引擎 |
| `log-collector/` | **删除** | Wazuh Agent + Grafana Alloy够用 |
| `ai-analyzer/` | **调整为ai-advisor/** | 专注AI能力 |
| `dashboard/` | **改为frontend/** | Vue.js前端 |

### 最终服务结构

```
AI-miniSOC/
├── frontend/                 # 🆕 Vue.js 3 前端
│   ├── src/
│   │   ├── views/           # 页面
│   │   ├── components/      # 组件
│   │   ├── stores/          # Pinia状态
│   │   └── api/             # API调用
│   └── package.json
│
├── backend/                  # 🆕 FastAPI 后端
│   ├── app/
│   │   ├── api/             # API路由
│   │   ├── models/          # 数据模型
│   │   ├── schemas/         # Pydantic模式
│   │   ├── services/        # 业务逻辑
│   │   └── core/            # 核心配置
│   └── requirements.txt
│
├── services/                 # 微服务（保留和新增）
│   ├── wazuh-api-proxy/     # ✅ 已实现
│   ├── asset-manager/       # 🆕 资产管理服务
│   ├── incident-workflow/   # 🆕 事件工作流服务
│   ├── exposure-scanner/    # 🆕 暴露面扫描（后期）
│   └── knowledge-base/      # 🆕 知识库（后期）
│
├── configs/                  # 配置文件
├── scripts/                  # 工具脚本
├── docs/                     # 文档
└── docker-compose.yml        # 容器编排
```

## 🎯 MVP v0.1 定义

### 时间周期
**6-8周**

### 核心功能（基于痛点）

#### 1. 资产管理
**解决痛点: Wazuh SOC功能不全**

- [ ] 手动添加资产（IP、名称、类型、负责人）
- [ ] 从Wazuh agent自动同步主机
- [ ] 资产分组（关键/重要/一般/测试）
- [ ] 资产标签（业务系统、环境等）
- [ ] 资产详情页（显示该资产的所有告警和事件）

#### 2. AI智能告警解释
**解决痛点: 告警看不懂**

- [ ] Wazuh告警 → AI中文解释
- [ ] 给出具体处置建议
- [ ] 风险等级智能评估
- [ ] AI分析结果缓存（避免重复调用）
- [ ] 支持多种开源模型API

**示例效果**:
```
原始告警:
"SSH login attempt failed. User: root, IP: 192.168.1.100,
Rule: 5710 (SSHD: Failed login attempt), Level: 5"

AI解释:
"检测到SSH暴力破解攻击
━━━━━━━━━━━━━━━━━━━━━━━━
风险等级: 中等

发生了什么:
有人正在尝试暴力破解你的SSH服务，尝试用root用户登录。
攻击来源: 192.168.1.100
失败次数: 3次

影响评估:
- 如果密码较弱，可能被攻破
- 成功后攻击者获得系统完全控制权

处置建议:
1. 立即检查192.168.1.100是否为内网合法IP
2. 如果是攻击IP，在防火墙中封禁
3. 检查是否有成功登录记录
4. 考虑启用密钥认证，禁用密码登录
5. 安装fail2ban自动防护"
```

#### 3. 事件工作流
**连接资产和告警**

- [ ] 从Wazuh告警一键创建事件
- [ ] 事件状态管理（新/处理中/已解决/关闭）
- [ ] 添加处理笔记
- [ ] 事件与资产关联
- [ ] 基础的事件列表和筛选

#### 4. Web界面（Vue.js）

- [ ] 资产管理页面
  - 资产列表（搜索、筛选、排序）
  - 资产详情（含关联告警）
  - 资产创建/编辑

- [ ] 事件管理页面
  - 事件列表（按状态、优先级筛选）
  - 事件详情（含AI分析）
  - 事件状态流转

- [ ] 告警查看页面
  - 集成Wazuh告警
  - 显示AI解释
  - 一键创建事件

- [ ] 概览仪表板
  - 资产统计
  - 事件统计
  - 高风险告警

### 不在MVP的功能

- ❌ 自动漏洞扫描（v0.2）
- ❌ 复杂的权限管理（v0.2）
- ❌ 自动化响应（v0.3）
- ❌ 自然语言查询（v0.3）
- ❌ 合规报告（v0.3）
- ❌ 威胁狩猎功能（v0.3）

## 🗄️ 数据模型

### 核心表结构

```sql
-- 资产表
CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    ip_address INET UNIQUE,
    mac_address MACADDR,
    asset_type VARCHAR(50),  -- server/workstation/printer/router/other
    criticality VARCHAR(20) CHECK (criticality IN ('critical', 'high', 'medium', 'low')),
    owner VARCHAR(255),
    business_unit VARCHAR(255),
    description TEXT,
    wazuh_agent_id VARCHAR(100),  -- 关联Wazuh agent
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 事件表
CREATE TABLE incidents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    severity VARCHAR(20) CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    wazuh_alert_id VARCHAR(100),  -- 关联Wazuh告警
    assigned_to VARCHAR(255),
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    ai_analysis_id INTEGER REFERENCES ai_analyses(id)
);

-- 资产-事件关联
CREATE TABLE asset_incidents (
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, incident_id)
);

-- AI分析缓存（避免重复调用API）
CREATE TABLE ai_analyses (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(100) UNIQUE NOT NULL,  -- Wazuh alert ID
    alert_fingerprint VARCHAR(100),  -- 告警指纹（相同类型可复用）
    explanation TEXT,  -- AI解释
    risk_assessment TEXT,  -- 风险评估
    recommendations TEXT,  -- 处置建议
    model_name VARCHAR(100),  -- 使用的模型
    model_version VARCHAR(50),  -- 模型版本
    tokens_used INTEGER,
    cost DECIMAL(10, 4),  -- 成本（人民币）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP  -- 缓存过期时间
);

-- 资产标签
CREATE TABLE asset_tags (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    tag_key VARCHAR(50),  -- 标签键: environment, business_system, etc.
    tag_value VARCHAR(100),  -- 标签值: production, hr-system, etc.
    UNIQUE(asset_id, tag_key)
);

-- 事件时间线（处理记录）
CREATE TABLE incident_timeline (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE CASCADE,
    action_type VARCHAR(50),  -- status_change, note, assignment, etc.
    action_data JSONB,  -- 详细数据
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_assets_ip ON assets(ip_address);
CREATE INDEX idx_assets_wazuh ON assets(wazuh_agent_id);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_created ON incidents(created_at DESC);
CREATE INDEX idx_ai_analyses_alert ON ai_analyses(alert_id);
CREATE INDEX idx_ai_analyses_fingerprint ON ai_analyses(alert_fingerprint);
```

## 🚀 实施路线图

### 第1周：需求与设计
- [ ] 创建产品需求文档 (`docs/prd.md`)
- [ ] 绘制详细的数据流图
- [ ] 绘制前端原型（手绘或工具）
- [ ] 确定AI模型服务商（申请API key）
- [ ] 搭建开发环境（Vue + FastAPI）

### 第2周：项目初始化
- [ ] 初始化FastAPI项目结构
- [ ] 初始化Vue.js项目
- [ ] 配置PostgreSQL数据库
- [ ] 创建数据库表和ORM模型
- [ ] 配置Docker Compose（开发环境）
- [ ] 编写基础配置（环境变量、日志等）

### 第3-4周：后端开发
- [ ] 实现资产CRUD API
- [ ] 实现Wazuh API集成（拉取告警、agent）
- [ ] 实现AI分析服务（告警解释）
- [ ] 实现AI缓存机制
- [ ] 实现事件CRUD API
- [ ] 实现JWT认证
- [ ] 编写API测试

### 第5-6周：前端开发
- [ ] 搭建Vue项目结构
- [ ] 实现资产列表和详情页
- [ ] 实现事件列表和详情页
- [ ] 实现告警查看页（集成AI解释）
- [ ] 实现概览仪表板
- [ ] 前后端联调

### 第7周：测试与优化
- [ ] 端到端测试
- [ ] 性能优化（AI缓存、查询优化）
- [ ] 安全检查（SQL注入、XSS等）
- [ ] 修复bug
- [ ] 编写用户文档

### 第8周：部署与发布
- [ ] 准备生产环境配置
- [ ] Docker镜像构建
- [ ] 部署到服务器
- [ ] 内部测试
- [ ] 收集反馈
- [ ] v0.1发布

## 💡 开发协作模式

### 团队构成
- **你**: 产品决策、业务逻辑、整体方向
- **我 (Claude)**: 代码实现、技术细节、文档编写

### 工作流程
1. **你**: 提出需求或确认方向
2. **我**: 实现代码 + 解释思路
3. **你**: 测试 + 反馈
4. **我**: 修改优化

### 最佳实践
- 先讨论清楚再动手（避免返工）
- 代码先本地测试，没问题再提交
- 重要改动先写文档说明
- 保持commit message清晰

## ❓ 待确认事项

### 近期需确认
1. **AI模型服务商**: 用通义千问/智谱/DeepSeek？
2. **数据库**: 是否已有PostgreSQL实例？
3. **部署环境**: 在哪台服务器部署？
4. **域名**: Web界面需要域名吗？

### 功能优先级
1. **MVP范围**: 以上定义是否合适？
2. **资产管理字段**: 还需要哪些字段？
3. **AI解释风格**: 技术详细 / 简洁易懂 / 两者可选？

### 时间安排
1. **可用时间**: 每周能投入多少小时？
2. **目标时间**: 希望多久能用上基础版本？
3. **里程碑**: 是否需要中间版本检查点？

## 📚 技术文档

### FastAPI
- 官方文档: https://fastapi.tiangolo.com/
- 中文教程: https://fastapi.apachecn.org/

### Vue.js 3
- 官方文档: https://cn.vuejs.org/
- Element Plus: https://element-plus.org/zh-CN/

### SQLAlchemy 2.0
- 官方文档: https://docs.sqlalchemy.org/en/20/

### 开源模型API
- 通义千问: https://help.aliyun.com/zh/dashscope/
- 智谱AI: https://open.bigmodel.cn/
- DeepSeek: https://platform.deepseek.com/

## 📝 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-03-18 | 初始版本，基于需求讨论创建 | Claude |

---

**下一步行动**:
1. 确认AI模型服务商并申请API Key
2. 确认数据库部署方案
3. 搭建基础开发环境
4. 开始第1周的设计工作
