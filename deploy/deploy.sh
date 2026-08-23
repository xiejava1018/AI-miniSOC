#!/bin/bash
###############################################################################
# AI-miniSOC Production Deploy Script
# 调用方式: bash deploy.sh <commit_sha> [message]
#   - commit_sha: 要部署的 git commit (full or short)
#   - message:   可选，部署说明（写入日志）
#
# 设计 (v2.2 修复 R5/R7):
#   1. 备份当前 commit + .env
#   2. git fetch + reset --hard 到目标 commit
#   3. 检查无 uncommitted
#   4. pip install backend deps
#   5. alembic check（不升级，仅告警）
#   6. npx vite build 前端（旁路构建 dist.new + 原子替换，不中断服务）
#   7. systemctl restart aisoc-backend
#   8. 健康检查：HTTP 端点 + DB 探活（v2.2 加）
#   9. 任何步骤失败 → 全局 trap 自动 git reset 回滚 (R5 修复)
#
# 前置条件:
#   - 项目位于 /home/xiejava/AIproject/AI-miniSOC
#   - systemd unit aisoc-backend 已创建
#   - 当前用户 xiejava 有 sudo 权限（systemctl）
#   - 服务器 .env 中 DB_NAME=AI-miniSOC-db（生产库，**不要混用本地 Mac 的 testdb**）
###############################################################################

set -euo pipefail

PROJECT_DIR=/home/xiejava/AIproject/AI-miniSOC
LOG_FILE=/tmp/aisoc-deploy.log
BACKUP_DIR=/home/xiejava/.aisoc-backups
BACKUP_SHA_FILE=/tmp/aisoc.previous_sha
HEALTH_URL_HTTP=http://127.0.0.1:8000/api/v1/public/system-info
HEALTH_URL_DB_URL_KEY=DB_NAME  # 用于 psql 探活

mkdir -p "$BACKUP_DIR"

# ===== 0. 参数检查 =====
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <commit_sha> [message]" >&2
    exit 1
fi

TARGET_SHA="$1"
MESSAGE="${2:-手动部署}"

log() {
    local ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" | tee -a "$LOG_FILE"
}

# ===== 前端构建：旁路构建 + 原子替换 =====
# 两个约束必须同时满足：
#  a) 不能增量堆积。vite 未开 emptyOutDir，原地 build 会让历次旧 chunk 永久累积，
#     既涨磁盘，也让「当前生效的是哪个构建」无法判断（排查部署 #62 时被误导过）。
#  b) 不能中断服务。nginx 的 root 直指 src/frontend/dist，该目录在 build 期间
#     不存在的话，全站立即 403。
# 最早的写法（先 mv dist 走再 build）满足 a 但破了 b，已实测造成部署 #65
# 期间前端 403 约 80 秒。现在先 build 到 dist.new，成功后用两次 rename 切换：
# 窗口微秒级，且 build 失败时 dist 根本没被动过。
build_frontend() {
    cd "$PROJECT_DIR/src/frontend"
    rm -rf dist.new dist.old
    if npx vite build --outDir dist.new --emptyOutDir 2>&1 | tail -20 | tee -a "$LOG_FILE" \
       && [[ -f dist.new/index.html ]]; then
        # 同文件系统 rename，nginx 不会观察到缺失的 root
        if [[ -d dist ]]; then
            mv dist dist.old
        fi
        mv dist.new dist
        rm -rf dist.old
        local entry
        entry=$(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' dist/index.html | head -1 || true)
        log "前端 build 完成，dist 已原子替换（入口: ${entry:-unknown}）"
        return 0
    fi
    rm -rf dist.new
    log "ERROR: vite build 失败；dist 未变动，前端继续服务旧版本"
    return 1
}

# ===== 全局回滚 trap (R5 修复) =====
# 任何步骤失败（除 rollback_failed 标记外）→ 自动回滚到 PREVIOUS_SHA
ROLLBACK_DONE=0
rollback() {
    if [[ $ROLLBACK_DONE -eq 1 ]]; then
        log "回滚 trap 已执行过，跳过（避免无限递归）"
        return
    fi
    ROLLBACK_DONE=1

    local exit_code=$?
    log "============================================="
    log "  部署失败 (exit=$exit_code)，触发全局回滚"
    log "============================================="

    if [[ ! -f "$BACKUP_SHA_FILE" ]]; then
        log "ERROR: 无 PREVIOUS_SHA 记录 ($BACKUP_SHA_FILE)，无法回滚"
        log "  请人工检查: cd $PROJECT_DIR && git log --oneline -5"
        return
    fi

    local prev=$(cat "$BACKUP_SHA_FILE")
    log "回滚目标: $prev"
    log "回滚步骤 1/3: git reset --hard"
    cd "$PROJECT_DIR"
    git reset --hard "$prev" 2>&1 | tee -a "$LOG_FILE" || true

    log "回滚步骤 2/3: 重新 build 前端"
    build_frontend || log "WARN: 回滚 build 失败，前端可能停留在旧构建"

    log "回滚步骤 3/3: 重启 backend"
    sudo -n systemctl restart aisoc-backend 2>&1 || systemctl restart aisoc-backend 2>&1 || true

    log "============================================="
    log "  回滚完成。检查 $LOG_FILE 获取详细日志"
    log "  服务状态: sudo systemctl status aisoc-backend"
    log "============================================="
}
trap rollback ERR INT TERM

# ===== 1. 备份当前 commit + .env =====
log "====== 部署开始: target=$TARGET_SHA message=$MESSAGE ======"

cd "$PROJECT_DIR"

PREVIOUS_SHA=$(git rev-parse HEAD)
echo "$PREVIOUS_SHA" > "$BACKUP_SHA_FILE"
log "当前 commit: $PREVIOUS_SHA"

TS_TAG=$(date +%Y%m%d_%H%M%S)
[[ -f src/backend/.env ]] && cp src/backend/.env "$BACKUP_DIR/backend.env.$TS_TAG"
[[ -f src/frontend/.env ]] && cp src/frontend/.env "$BACKUP_DIR/frontend.env.$TS_TAG"
[[ -f src/collectors/.env ]] && cp src/collectors/.env "$BACKUP_DIR/collectors.env.$TS_TAG"
log ".env 已备份到 $BACKUP_DIR"

# ===== 2. 拉取 + reset =====
log "获取目标 commit: $TARGET_SHA"
# 三个 fetch 策略 (按优先顺序):
#   1) git fetch origin <sha>      直接拿这一个 commit (最快, 绕过 shallow 问题)
#   2) git fetch --depth=N origin  带深度 (易将 repo 变 shallow, 后续 fetch 会丢 commit)
#   3) git fetch --unshallow origin 兑底取消 shallow (全历史下载, 慢网可能超时但能修复)
# 注: 服务器到 github 带宽很慢 (~456 B/s), 全历史 fetch 几乎必超时
cd "$PROJECT_DIR"
if timeout 90 git fetch origin "$TARGET_SHA" 2>/dev/null; then
    log "  策略1成功: 直接拉取目标 commit"
elif timeout 120 git fetch --depth=200 origin master 2>/dev/null; then
    log "  策略2成功: --depth=200 pull"
else
    log "WARN: 前两策略都失败, 尝试 --unshallow (会下载全历史, 慢网可能超时)"
    timeout 300 git fetch --unshallow origin 2>/dev/null || log "WARN: unshallow 也失败, 仅靠本地 commit"
fi

# 验证目标 commit 存在
if ! git cat-file -t "$TARGET_SHA" >/dev/null 2>&1; then
    log "ERROR: 目标 commit $TARGET_SHA 不存在"
    exit 2
fi

log "git reset --hard $TARGET_SHA"
git reset --hard "$TARGET_SHA"

# ===== 3. 检查 uncommitted =====
if [[ -n "$(git status --porcelain)" ]]; then
    log "ERROR: reset 后仍有未提交文件:"
    git status --porcelain | tee -a "$LOG_FILE"
    exit 3
fi

# ===== 4. Backend deps =====
log "===== 更新 backend 依赖 ====="
cd "$PROJECT_DIR/src/backend"
./venv/bin/pip install -q --disable-pip-version-check -r requirements.txt 2>&1 | tail -20 | tee -a "$LOG_FILE"

# ===== 5. Alembic check（不升级）=====
log "===== alembic check (非阻塞，仅告警) ====="
# 故意不 set -e（已知 seed script 缺陷），记录 WARNING 即可
./venv/bin/alembic check 2>&1 | tee -a "$LOG_FILE" || log "WARN: alembic check 失败，模型与迁移不一致（已知问题，DBA 后续手动处理）"

# ===== 6. 前端 build =====
log "===== 前端 build (npx vite build) ====="
cd "$PROJECT_DIR/src/frontend"
npm ci --silent 2>&1 | tail -10 | tee -a "$LOG_FILE"
if ! build_frontend; then
    log "ERROR: 前端 build 失败"
    exit 4   # trap 会回滚
fi

# ===== 7. 重启 backend =====
log "===== 重启 backend ====="
sudo -n systemctl restart aisoc-backend 2>&1 || systemctl restart aisoc-backend 2>&1

# ===== 8. 健康检查 (R7 修复：HTTP + DB 双重探活) =====
log "===== 健康检查 (HTTP + DB 双重) ====="
HEALTH_OK=0
for i in 1 2 3 4 5; do
    sleep 2

    # 8.1 HTTP 端点（验证进程在）
    HTTP_RESP=$(curl -s --max-time 5 "$HEALTH_URL_HTTP" 2>/dev/null || echo "")
    if ! echo "$HTTP_RESP" | grep -q '"code":200'; then
        log "  [$i/5] HTTP 探活失败: $HTTP_RESP"
        continue
    fi

    # 8.2 DB 探活 (R7 修复：解决 /system-info 不查 DB 的假阳性)
    # 用 venv python + SQLAlchemy 探活 (不依赖 psql, 服务器可能没装 postgresql-client)
    DB_HOST=$(grep '^DB_HOST=' "$PROJECT_DIR/src/backend/.env" | cut -d= -f2 | tr -d '"' || echo "")
    DB_PORT=$(grep '^DB_PORT=' "$PROJECT_DIR/src/backend/.env" | cut -d= -f2 | tr -d '"' || echo "5432")
    DB_NAME=$(grep '^DB_NAME=' "$PROJECT_DIR/src/backend/.env" | cut -d= -f2 | tr -d '"' || echo "")
    DB_USER=$(grep '^DB_USER=' "$PROJECT_DIR/src/backend/.env" | cut -d= -f2 | tr -d '"' || echo "")
    DB_PASS=$(grep '^DB_PASSWORD=' "$PROJECT_DIR/src/backend/.env" | cut -d= -f2 | tr -d '"' || echo "")

    if [[ -z "$DB_HOST" || -z "$DB_NAME" ]]; then
        log "  [$i/5] WARN: .env 缺 DB_HOST/DB_NAME，跳过 DB 探活"
        HEALTH_OK=1
        break
    fi

    DB_RESP=$(cd "$PROJECT_DIR" && \
        DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASS="$DB_PASS" \
        src/backend/venv/bin/python deploy/db_healthcheck.py 2>/dev/null || echo "")
    if [[ "$DB_RESP" == "1" ]]; then
        log "  [$i/5] ✓ HTTP 200 + DB SELECT 1 OK"
        HEALTH_OK=1
        break
    else
        log "  [$i/5] DB 探活失败: $DB_RESP"
    fi
done

# ===== 9. 失败回滚（健康检查级别失败仍走 trap）=====
if [[ $HEALTH_OK -ne 1 ]]; then
    log "ERROR: 健康检查 5 次重试全部失败"
    exit 5   # trap 会回滚
fi

# ===== 10. 检查 alembic 落后 =====
log "===== 检查 alembic 版本 ====="
DB_NAME=$(grep '^DB_NAME=' "$PROJECT_DIR/src/backend/.env" | cut -d= -f2 | tr -d '"' || echo "")
log "生产 DB: $DB_NAME"
REMOTE_HEAD=$(cd "$PROJECT_DIR/src/backend" && ./venv/bin/alembic current 2>/dev/null | awk '{print $1}' | head -1)
LOCAL_HEAD=$(cd "$PROJECT_DIR/src/backend" && ./venv/bin/alembic heads 2>/dev/null | awk '{print $1}' | head -1)
log "生产 alembic: $REMOTE_HEAD"
log "代码 alembic: $LOCAL_HEAD"
if [[ -n "$LOCAL_HEAD" && -n "$REMOTE_HEAD" && "$REMOTE_HEAD" != "$LOCAL_HEAD" ]]; then
    log "WARN: 数据库落后于代码 - 需要 DBA 手动跑 alembic upgrade head"
    log "      $REMOTE_HEAD → $LOCAL_HEAD"
fi

# 成功 - 关闭 trap（不触发回滚）
trap - ERR INT TERM
ROLLBACK_DONE=1   # 防止任何后续错误触发回滚

# ===== 11. 采集器变更提示 =====
# 采集器容器不由本脚本部署（理由见 deploy/deploy_collectors.sh 头部注释：
# 不能让采集器 build 失败触发 backend 回滚）。CD workflow 会在本脚本之后自动
# 调 deploy_collectors.sh；但**手工**跑 deploy.sh 的人不会经过那一步，所以这里
# 明确提示一句，避免又出现「代码改了、线上镜像还是两周前那个」的情况。
if [[ -n "${PREVIOUS_SHA:-}" ]] \
   && ! git diff --quiet "$PREVIOUS_SHA" "$TARGET_SHA" -- src/collectors/ 2>/dev/null; then
    log "NOTE: 本次 src/collectors/ 有变更，采集器镜像需要重建"
    log "      CD 会自动执行；手工部署请补跑: bash deploy/deploy_collectors.sh"
fi

log "====== 部署成功: $TARGET_SHA ======"
log ""
exit 0
