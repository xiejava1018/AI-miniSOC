---
name: project-init
description: AI研发项目组织初始化技能，用于新项目初始化时生成 CLAUDE.md、目录结构、规范文件和基础设施配置模板
homepage: https://github.com/xiejava1018/AI-miniSOC
metadata: { "aisoc": { "emoji": "🏗️", "requires": { "modules": [] } } }
---

# 项目组织初始化技能

用于新项目初始化，一次性生成完整的项目上下文体系，让 Claude Code 从第一天就能高效协作。

## 触发条件

当用户说以下任何一种时触发：
- "初始化项目" / "初始化一个新项目"
- "项目初始化" / "新建项目"
- "初始化 AI 研发环境"
- "设置项目上下文"
- `/project-init`

## 执行步骤

### Step 0: 检查项目状态

检查当前目标目录（用户指定的项目目录）是否已有项目文件：

1. 首先向用户确认**项目目录路径**
2. 检查该目录下是否已有：
   - package.json / go.mod / requirements.txt / pom.xml 等包管理文件
   - .git 目录
   - 现有源码文件

**如果已有项目（适配模式）**：
- 自动解析技术栈：读取 package.json 的 dependencies、go.mod 等获取语言和框架
- 跳过 Step 1/2 中的技术栈提问
- 直接询问用户想补充哪些上下文

**如果无现有项目（新建模式）**：
- 继续完整的 Step 1 ~ Step 10

### Step 1: 收集项目信息（合并轮次）

向用户一次性收集以下信息（用 AskUserQuestion）：

**必填项：**
1. 项目名称和一句话描述
2. 技术栈（后端/前端/数据库/基础设施）
3. 项目类型：Web应用 / API服务 / CLI工具 / 库/SDK / 数据平台 / 其他

**选填项（有默认值）：**
4. 主要编程语言（默认根据技术栈推断）
5. 包管理器（npm/yarn/pnpm/pip/poetry/go mods/maven 等）
6. 是否需要 Docker 支持（默认是）
7. 是否需要 CI/CD 配置（默认是）
8. 团队规模（个人/小团队/大团队，影响规范复杂度）

**规范模板选择：**
9. 规范模板：简约型 / 标准型 / 严格型（见 Step 3 说明）

提示用户：基础设施信息如果没有可以跳过，后续有需要再补充。

### Step 2: 收集基础设施信息（可选）

向用户收集基础设施地址（用 AskUserQuestion）：

- 代码仓库地址（GitHub/GitLab/Gitea）
- 数据库地址和类型（PostgreSQL/MySQL/MongoDB/Redis 等）
- 测试环境地址
- 监控系统地址（Grafana/Prometheus 等）
- 日志系统地址（Loki/ELK 等）
- CI/CD 平台地址（Jenkins/GitHub Actions/GitLab CI 等）
- 其他内部服务地址

提示用户：**只提供地址和端口，不要提供密码和 Token。如果没有或暂时不清楚可以跳过。凭证信息后续通过 .env 配置。**

### Step 3: 生成目录结构

根据项目类型和技术栈，生成标准目录结构。通用结构如下：

```
project-root/
├── CLAUDE.md                    # Claude Code 项目指令（核心上下文文件）
├── .claude/
│   ├── settings.json            # Hooks 和权限配置
│   └── skills/                  # 项目自定义技能（可选）
├── .env.example                 # 环境变量模板（只有 key 没有 value）
├── .gitignore
├── docs/
│   ├── architecture/
│   │   └── overview.md          # 技术架构概览
│   ├── decisions/               # 架构决策记录 (ADR)
│   │   └── template.md          # ADR 模板
│   └── runbooks/                # 运维手册
│       └── template.md          # Runbook 模板
├── configs/                     # 配置文件（非敏感）
├── scripts/                     # 工具脚本
└── tests/                       # 测试
```

针对不同项目类型，追加特定目录：

**Web 应用 / API 服务：**
```
├── src/                         # 或 internal/ + pkg/ (Go 项目)
│   ├── api/                     # API 路由和处理器
│   ├── models/                  # 数据模型
│   ├── services/                # 业务逻辑
│   └── utils/                   # 工具函数
├── migrations/                  # 数据库迁移
├── api-docs/                    # API 文档
```

**前端项目：**
```
├── src/
│   ├── components/              # 组件
│   ├── pages/                   # 页面
│   ├── hooks/                   # 自定义 Hooks
│   ├── services/                # API 调用
│   ├── stores/                  # 状态管理
│   └── utils/                   # 工具函数
├── public/                      # 静态资源
```

**数据平台：**
```
├── pipelines/                   # 数据管道
├── models/                      # 数据模型
├── queries/                     # SQL/查询
├── notebooks/                   # 分析笔记本
└── data/                        # 数据样本/配置
```

### Step 4: 生成 CLAUDE.md

根据 Step 1 中用户选择的规范模板，**读取对应模板文件**并填入信息：

- **简约型** → 读取 `skills/project-init/templates/minimal/CLAUDE.md.tpl`
- **标准型** → 读取 `skills/project-init/templates/standard/CLAUDE.md.tpl`
- **严格型** → 读取 `skills/project-init/templates/strict/CLAUDE.md.tpl`

将收集的信息填入模板中的占位符 `{xxx}`，生成最终的 `CLAUDE.md` 放到项目根目录。

**占位符替换说明：**
- `{项目名称}` / `{一句话描述}` / `{技术栈详情}` → 来自 Step 1
- `{目录结构}` → 来自 Step 3
- `{服务名}` / `{地址}` / `{用途}` → 来自 Step 2
- `{安装命令}` / `{测试命令}` 等 → 根据技术栈自动生成

### Step 5: 生成 .env.example

读取模板文件 `skills/project-init/templates/env-example.tpl`，根据 Step 2 收集的基础设施信息补充环境变量，生成项目根目录的 `.env.example`。

### Step 6: 生成规范文件

读取模板文件并复制到项目的 `docs/` 目录下：

- `templates/architecture-overview.md` → `docs/architecture/overview.md`
- `templates/adr-template.md` → `docs/decisions/template.md`
- `templates/runbook-template.md` → `docs/runbooks/template.md`

### Step 7: 生成 .claude/settings.json

生成基础的 Claude Code 配置文件 `.claude/settings.json`：

```json
{
  "permissions": {
    "allow": [],
    "deny": []
  },
  "hooks": {}
}
```

**前置检查**：根据技术栈自动配置 hooks 前，先确认项目中是否已安装对应工具：

- JavaScript/TypeScript 项目：检查 package.json 中是否有 eslint/prettier，有则配置 hooks
- Python 项目：检查 requirements.txt 或 pyproject.toml 中是否有 black/flake8，有则配置 hooks
- Go 项目：直接配置 go fmt/go vet（Go 自带工具）

如果对应工具未安装，跳过 hooks 配置，并在最终提示中告知用户。

### Step 8: 生成 .gitignore

根据技术栈生成合适的 .gitignore 文件，确保：
- 排除 .env（凭证文件）
- 排除编译产物和依赖目录
- 排除 IDE 配置
- 保留 .env.example

### Step 9: 确认和调整

生成完成后：
1. 展示完整的目录结构树
2. 提示用户检查 CLAUDE.md 内容是否符合预期
3. 提示用户补充 .env 中的凭证信息
4. 提示用户运行 `git init`（如果尚未初始化）

## 输出要求

- 所有文件使用 UTF-8 编码
- Markdown 文件中文优先
- 变量名、代码注释用英文
- 不生成任何包含凭证的文件
- 目录结构合理，不要过度设计

## 注意事项

- 这是一个交互式技能，需要多轮收集信息
- 不要假设用户的技术栈，必须通过提问确认
- 规范文件是模板，用户需要根据实际情况调整
- 基础设施地址只记录非敏感信息（IP、端口、URL）
- 凭证相关的 key 名称可以记录在 .env.example 中，但 value 必须留空

## 与其他工具集成

初始化完成后，用户可以：
- 使用 `/commit` 技能进行规范化提交
- 在 CLAUDE.md 中逐步补充项目特有的上下文信息

---

**版本**: v1.1.0
**最后更新**: 2026-04-08
**作者**: xiejava
