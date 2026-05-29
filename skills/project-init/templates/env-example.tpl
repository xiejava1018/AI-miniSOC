# ============================================
# {项目名称} - 环境变量配置模板
# 使用方法: cp .env.example .env 然后填入实际值
# 注意: .env 文件已加入 .gitignore，不会被提交
# ============================================

# ---------- 应用配置 ----------
APP_ENV=development
APP_PORT=3000
APP_DEBUG=true
APP_SECRET=

# ---------- 数据库 ----------
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_POOL_SIZE=10

# ---------- 缓存 ----------
REDIS_HOST=
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ---------- 消息队列 ----------
# MQ_HOST=
# MQ_PORT=
# MQ_USER=
# MQ_PASSWORD=

# ---------- 对象存储 ----------
# OSS_ENDPOINT=
# OSS_ACCESS_KEY=
# OSS_SECRET_KEY=
# OSS_BUCKET=

# ---------- 监控 ----------
# GRAFANA_URL=
# PROMETHEUS_URL=
# LOKI_URL=
# APM_URL=

# ---------- 第三方服务 ----------
# {根据项目需要的第三方服务补充}

# ---------- CI/CD ----------
# DOCKER_REGISTRY=
# DEPLOY_KEY=

# ---------- 日志 ----------
LOG_LEVEL=info
LOG_FORMAT=json
