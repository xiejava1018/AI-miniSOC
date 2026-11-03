<!-- 
Conventional Commits：feat / fix / docs / refactor / test / chore / perf / ci
示例：feat: 资产稽核新增按业务系统分组
-->

## 变更说明

<!-- 做了什么、为什么做（关联 Issue 编号，如 closes #12） -->

## 变更类型

- [ ] feat（新功能）
- [ ] fix（缺陷修复）
- [ ] refactor（重构，不改行为）
- [ ] docs（文档）
- [ ] test（测试）
- [ ] chore / ci（工程化）

## 自查清单

- [ ] 后端变更：已跑 `pytest`（tests/ 目录全绿）；涉及权限/路由的变更已跑 `tests/security/`（阻断式门禁，不许 skip）
- [ ] 前端变更：`npm run lint` 与 `vue-tsc` 通过
- [ ] 写路由挂了带 AuthSpec 的显式授权依赖（参见 app/core/route_security.py；写侧默认拒绝，漏挂会被兜底拦截 + CI 失败）
- [ ] 新增表结构变更已有对应 alembic 迁移（迁移历史不允许断档）
- [ ] 涉及 AI 消费点的变更已确认降级路径（AI 不可用时行为明确）
- [ ] 已更新相关文档（README / docs/design / CLAUDE.md 决策记录，如适用）

## 测试证据

<!-- 贴关键测试输出 / 截图。安全相关变更必须附「viewer 写被 403」类验证截图 -->
