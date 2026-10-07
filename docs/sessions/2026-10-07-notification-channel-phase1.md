# 2026-10-07：通知通道 + 偏好 + dispatcher 框架（OH-NOT-F2 · Phase 1）

> 主题：通知系统扩展 + SMTP 可配置 + 多通道分发
> commit: `4b5c261 ✨ OH-NOT-F2 Phase 1`
> alembic head: `s5t6u7v8w9x0`（dev testdb）/ `l8c9d0e1f2a3`（102 prod 待 cherry-pick）

## 用户需求

> "邮件通知的 smtp 服务要支持可配置"

完整规划见本 commit docstring + CLAUDE.md §0/§1/§4.3 红线全遵循。

## Phase 1 交付（commit `4b5c261`）

### 数据库（3 张新表）

| 表 | 用途 | 关键字段 |
|---|---|---|
| `soc_notification_channels` | 通道字典（inbox + email + 未来 sms/webhook）| code UNIQUE / enabled / config_json (JSONB) |
| `soc_notification_dispatch_logs` | 每通道投递日志 | status (pending/sent/failed/bounced/skipped_pref) / retry_count / next_retry_at |
| `soc_notification_user_prefs` | 用户 per (type, channel) 偏好 | UNIQUE(user_id, type, channel_code) |

预置数据：`inbox` (enabled=true, config={}) + `email` (enabled=false, config={} 等待 admin 配)

### 代码层

| 文件 | 行数 | 内容 |
|---|---:|---|
| `app/models/notification_channel.py` | 158 | NotificationChannel + DispatchLog + UserPref 三个 ORM |
| `app/schemas/notification_channel.py` | 130 | admin / user 双套 Pydantic schema |
| `app/services/notification_channel_service.py` | 220 | 通道 CRUD + email config 校验 + 60s 缓存 + password fernet 加密 |
| `app/services/notification_dispatcher.py` | 200 | inbox=同步sent / email=写pending（Phase 1 不真发）/ 异常隔离每通道 |
| `app/api/notification_channels.py` | 140 | admin 通道管理 4 个端点 + test 端点 (Phase 1 仅 socket test) |
| `app/api/notification_preferences.py` | 50 | 用户 2 个端点 (GET my / PUT my/(type,channel)) |
| `app/services/notification_service.py` | +82 | 新增 `create_multi()` 多用户多通道入口 |
| `app/api/__init__.py` | +5 | 注册新 routers |
| `app/models/__init__.py` | +8 | 导出新 models |
| `alembic/versions/s5t6u7v8w9x0_*.py` | 180 | 3 表 CREATE + 2 通道预置 (CREATE/INSERT 都 IF NOT EXISTS 幂等) |

### API 端点

```
GET    /api/v1/notification-channels                  列出所有通道（password 自动脱敏 ***）
GET    /api/v1/notification-channels/{id}              详情
PUT    /api/v1/notification-channels/{id}              admin 更新（仅 email 完整校验 SMTP 字段）
POST   /api/v1/notification-channels/{id}/test        admin 测试 — Phase 1 仅 SMTP socket connect (5s timeout)

GET    /api/v1/notification-preferences/my             我的偏好 (空 = 默认全收)
PUT    /api/v1/notification-preferences/my/{type}/{channel_code}  upsert 偏好
```

### 配置规范 (Phase 1 SMTP email config_json)

```json
{
  "host": "smtp.gmail.com",          // 必填
  "port": 587,                       // 必填, 1-65535
  "user": "admin@example.com",       // 必填
  "password": "****",                // 必填, fernet 加密 (gAAAAA 前缀)
  "from_addr": "admin@example.com",  // 必填, 邮箱格式
  "use_tls": true,                   // 可选, 默认 true
  "from_name": "AI-miniSOC 通知",     // 可选
  "max_retries": 3,                  // 可选, 默认 3
  "retry_backoff_seconds": 60        // 可选, 默认 60
}
```

## 端到端验证（commit 前实测）

```
✅ alembic upgrade s5t6u7v8w9x0 on dev testdb → 3 表创建 + 2 通道预置
✅ GET /notification-channels → 2 通道 (inbox enabled, email disabled)
✅ PUT /notification-channels/2 → password 入参 → fernet 加密 (gAAAAA) → DB 存储
✅ GET /notification-channels/2 → password 返回 "***" (安全脱敏)
✅ POST /notification-channels/2/test → SMTP socket connect smtp.gmail.com:587 → 10ms 成功
✅ PUT /notification-preferences/my/push:eol_warning/email enabled=false
✅ GET /notification-preferences/my → 1 条偏好正确显示
✅ create_multi([1,2,3], type='test') → 3 Notification + 6 dispatch_logs
✅ dispatcher 写出: inbox=sent×3 (同步) + email=pending×3 (Phase 1 写日志不真发)
✅ X1 矩阵默认: user 1 pref 禁用 (push:eol_warning, email) 但 type='test' 没禁用 → 仍收 email
   (验证 per-(type, channel) 粒度正确, 不会一禁全禁)
```

## 关键设计决策

1. **dispatcher 异常隔离**: 每个通道独立 try/except，单通道失败不阻断其他通道 (CLAUDE.md §4.13 假阴性预防)
2. **password fernet 加密**: encryption_service.encrypt_if_needed(force=True) 强制重加密避免 IDEMPOTENT 误判 (CLAUDE.md §0/§1.7)
4. **配置走 DB 不走 env**: CLAUDE.md §0 配置中心 11 个调用点迁移 + §1.7 三库严格分离
5. **API 出参脱敏**: NotificationChannelOut 的 config_json 经 `_redact_config()` 把 password 替换为 "***"
6. **admin only**: 通道 PUT + test 端点都用 `Depends(require_admin())` (CLAUDE.md §1.3)
7. **per-(type, channel) 偏好粒度**: UNIQUE (user_id, type, channel_code)，用户可精细控制
8. **Phase 1 dispatcher 不真发邮件**: email 通道只写 dispatch_logs(status=pending)，Phase 2 worker 接管 (CLAUDE.md §4.7 「分阶段发布」)

## Phase 2 待办（不在本 commit 范围）

- [ ] `app/services/email_sender.py` — aiosmtplib 异步 SMTP 投递
- [ ] `app/services/email_notifier_worker.py` — 60s tick 扫 pending dispatch_logs 队列
- [ ] `configs/templates/notifications/{type}.{html,txt}.j2` — Jinja2 模板
- [ ] admin 通道配置前端页 `views/system/notification-channels/index.vue`
- [ ] 用户偏好前端页 `views/profile/notification-preferences/index.vue`
- [ ] 菜单入口: 「系统管理 → 通知通道」(admin) + 「个人中心 → 通知偏好」(user)
- [ ] alembic 加 FK 约束 (notification_id → soc_notifications.id) — Phase 1 暂留软引用

## 102 prod 部署指南

```bash
# 102 上同步本 commit + 跑 alembic
ssh xiejava@192.168.0.102
cd /home/xiejava/AIproject/AI-miniSOC
git fetch origin master
git cherry-pick 4b5c261   # 或 git reset --hard origin/master (master 全量同步)
cd src/backend
venv/bin/alembic upgrade head
sudo systemctl restart aisoc-backend
```

## 相关 CLAUDE.md 章节

- §0 配置中心 + §1.7 三库严格分离 + §1.3 admin bypass + §3.2 模块化
- §4.3 迁移 4 条红线 + §4.7 分阶段发布 + §4.13 假阴性预防
- §5 session 笔记归档规则（本文件）