# project-init — AI 研发项目组织初始化技能

一键生成 Claude Code 所需的完整项目上下文体系，让 AI 辅助开发从第一天就高效运转。

## 它解决什么问题

开始一个新项目时，Claude Code 对项目一无所知。每次都要重复解释技术栈、规范、基础设施地址。这个技能通过交互式问答，一次性生成所有上下文文件，让 Claude Code 立刻理解你的项目。

**已有项目也能用** — 如果项目已有代码，会自动进入适配模式，只补充缺失的上下文文件，不改动任何已有代码。

## 它生成什么

| 文件 | 作用 |
|------|------|
| `CLAUDE.md` | Claude Code 的核心上下文文件，每次对话自动加载 |
| `.env.example` | 环境变量模板（只有 key，不含密码） |
| `.claude/settings.json` | Hooks 和权限配置，根据技术栈自动设置 |
| `.gitignore` | 排除 .env、编译产物、IDE 配置 |
| `docs/architecture/overview.md` | 技术架构文档模板 |
| `docs/decisions/template.md` | 架构决策记录（ADR）模板 |
| `docs/runbooks/template.md` | 运维手册模板 |

## 安装

### 全局安装（推荐）

安装到 `~/.claude/skills/` 后，在任意目录下都可以使用：

```bash
cp -r skills/project-init ~/.claude/skills/project-init
```

### 项目级安装

将 `skills/project-init/` 目录保留在项目仓库中，团队成员 clone 后即可使用。同时在 `.claude/commands/` 下创建入口文件：

```bash
mkdir -p .claude/commands
cat > .claude/commands/project-init.md << 'EOF'
按照 skills/project-init/SKILL.md 中定义的项目初始化流程，帮我初始化一个新项目。
EOF
```

## 如何使用

### 方式一：斜杠命令（推荐）

```
/project-init
```

### 方式二：对话触发

直接说：

```
初始化一个新项目
```

或：

```
按照 skills/project-init/SKILL.md 的流程，帮我初始化项目
```

### 方式三：Skill 调用

```
/skill project-init
```

## 使用流程

### 新建项目

整个过程是交互式的，分 3 轮问答：

**第 1 轮 — 项目信息 + 规范选择**
- 项目名称、描述、技术栈
- 项目类型（Web应用/API服务/CLI工具/库/数据平台）
- 规范模板（简约型/标准型/严格型）
- 团队规模、Docker/CI/CD 需求

**第 2 轮 — 基础设施地址（可选，可跳过）**
- 代码仓库、数据库、测试环境
- 监控、日志、CI/CD 等内部服务
- 只填地址和端口，不填密码

**第 3 轮 — 自动生成**
- 创建目录结构
- 根据模板生成所有文件
- 展示结果供你确认

### 已有项目适配

如果目标目录已有代码（package.json / go.mod / requirements.txt 等），会自动进入**适配模式**：

1. 自动解析技术栈（读取依赖文件获取语言和框架）
2. 扫描现有目录结构，只补充缺失的上下文文件
3. 跳过技术栈提问，只问"你想补充哪些上下文"
4. 已有的 `.gitignore` 合并而非覆盖
5. 已有的 `CLAUDE.md` 提示选择覆盖或合并

**不会改动任何已有代码和配置。**

### 规范模板对比

| 模板 | 适用场景 | 规范范围 |
|------|----------|----------|
| 简约型 | 个人项目、2-3人小团队 | 基础编码风格 + Git 规范 |
| 标准型 | 3-10人团队 | 完整编码规范 + API规范 + 测试规范 |
| 严格型 | 10+人大团队、生产级系统 | 全面规范 + Review流程 + 数据库规范 |

## 支持的项目类型

- **Web 应用** — 前后端分离的完整 Web 项目
- **API 服务** — 后端 API 或微服务
- **CLI 工具** — 命令行工具
- **库/SDK** — 供其他项目引用的代码库
- **数据平台** — 数据管道、分析、ETL

每种类型会生成对应的目录结构。

## 文件结构

```
skills/project-init/
├── SKILL.md                              # 技能定义（执行流程）
├── README.md                             # 本文件
├── config.json                           # 技能配置
├── .source.json                          # 源信息
└── templates/
    ├── minimal/CLAUDE.md.tpl             # 简约型 CLAUDE.md 模板
    ├── standard/CLAUDE.md.tpl            # 标准型 CLAUDE.md 模板
    ├── strict/CLAUDE.md.tpl              # 严格型 CLAUDE.md 模板
    ├── adr-template.md                   # 架构决策记录模板
    ├── architecture-overview.md          # 技术架构文档模板
    ├── runbook-template.md               # 运维手册模板
    └── env-example.tpl                   # 环境变量模板
```

## 注意事项

- **凭证安全**：所有密码和 Token 通过 `.env` 管理，不会出现在生成的文件中。生成后记得 `cp .env.example .env` 并填入实际值
- **模板可调**：生成的文件都是模板和起点，请根据项目实际情况修改。CLAUDE.md 不是生成后就固定的，应该随项目演进持续更新
- **不要过度设计**：个人项目选简约型就够了，规范太重反而降低效率
- **地址变更**：基础设施地址变化时记得同步更新 CLAUDE.md
- **Git 初始化**：如果目标目录还没有 `git init`，生成后记得初始化

## 生成后建议做的事

1. 检查 `CLAUDE.md` 内容是否符合预期，补充遗漏的约束
2. 填写 `.env` 中的凭证信息
3. 根据实际需要调整目录结构
4. `git init` + 首次提交
5. 如果是大项目，在关键子目录下追加模块级 `CLAUDE.md`

## 与其他工具集成

初始化完成后，用户可以：
- 使用 `/commit` 技能进行规范化提交
- 在 CLAUDE.md 中逐步补充项目特有的上下文信息

---

**版本**: v1.1.0
**最后更新**: 2026-04-08
