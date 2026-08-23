#!/bin/bash
###############################################################################
# AI-miniSOC 采集器容器部署
#
# 调用方式: bash deploy/deploy_collectors.sh [--force]
#   --force   跳过路径变更检测，无条件重建
#
# ---------------------------------------------------------------------------
# 为什么独立成一个脚本，而不并入 deploy.sh
# ---------------------------------------------------------------------------
# deploy.sh 有一个全局回滚 trap：任何步骤失败就 git reset 回上一个 commit。
# 采集器镜像 build 失败（比如 PyPI 抽风）**不应该**把已经部署成功并通过健康
# 检查的 backend 回滚掉 —— 两者生命周期完全独立（采集器在 docker，backend 在
# systemd）。所以本脚本由 CD 在 deploy.sh 成功之后单独执行，失败只让 workflow
# 变红，不碰 backend。
#
# ---------------------------------------------------------------------------
# 为什么默认按路径变更触发，而不是每次 push 都重建
# ---------------------------------------------------------------------------
# build 要跑 pip install，耗时且吃 PyPI 网络；而 src/collectors/ 极少变动
# （2026-08-08 之后两周一次没动过）。每次 push 都 rebuild 纯属浪费，还会无谓
# 打断采集 —— 重建容器 = 丢一个采集周期。
#
# ---------------------------------------------------------------------------
# 历史背景（为什么会有这个脚本）
# ---------------------------------------------------------------------------
# 在此之前 src/collectors/ **完全在 CI/CD 之外**：镜像是 2026-08-08 手工
# build 的，RestartCount=0，git 里的采集器代码改了也永远进不到线上。
# 直接后果：tplink 的 --test 分支有个双事件循环 bug，导致 docker HEALTHCHECK
# 连续失败 20531 次、容器 unhealthy 整整 14 天，且每次漏一个不被回收的
# healthcheck 子进程（累计 233 个 <defunct>）。修好代码也不会自动生效，
# 必须有人记得手动 docker compose build —— 这个「记得」就是缺口本身。
###############################################################################

set -euo pipefail

PROJECT_DIR=/home/xiejava/AIproject/AI-miniSOC
COLLECTORS_DIR="$PROJECT_DIR/src/collectors"
# 与 deploy.sh 共用日志：CD 的「Show final state」步骤会 cat 这个文件，
# 采集器的部署过程也就一并可见，不用再找第二个日志。
LOG_FILE=/tmp/aisoc-deploy.log
BACKUP_SHA_FILE=/tmp/aisoc.previous_sha
HEALTH_WAIT_SECONDS=200

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] [collectors] $*" | tee -a "$LOG_FILE"
}

log "===== 采集器部署开始 (force=$FORCE) ====="

cd "$PROJECT_DIR"

# ===== 0. 前置检查 =====
if ! command -v docker >/dev/null 2>&1; then
    log "ERROR: 未找到 docker，无法部署采集器"
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    log "ERROR: docker compose (v2 插件) 不可用"
    exit 1
fi
if [[ ! -f "$COLLECTORS_DIR/docker-compose.yaml" ]]; then
    log "ERROR: $COLLECTORS_DIR/docker-compose.yaml 不存在"
    exit 1
fi
# .env 带 MINISOC_API_KEY / ROUTER_PASSWORD / WAZUH_PASSWORD，是 gitignore 的，
# 只在服务器本地存在。缺了 compose 会用空默认值把容器起起来然后一直认证失败，
# 那种「起来了但没用」比直接失败更难查，所以这里硬拦。
if [[ ! -f "$COLLECTORS_DIR/.env" ]]; then
    log "ERROR: $COLLECTORS_DIR/.env 不存在 —— 缺少采集器凭证，拒绝部署"
    log "      （该文件不入 git，需人工维护；deploy.sh 每次会备份到 ~/.aisoc-backups）"
    exit 1
fi

# ===== 1. 路径变更检测 =====
CURRENT_SHA=$(git rev-parse HEAD)
if [[ $FORCE -eq 0 ]]; then
    if [[ ! -f "$BACKUP_SHA_FILE" ]]; then
        log "WARN: 无 $BACKUP_SHA_FILE，无法判断变更范围 —— 本次跳过"
        log "      如需强制重建: bash deploy/deploy_collectors.sh --force"
        exit 0
    fi
    PREVIOUS_SHA=$(cat "$BACKUP_SHA_FILE")
    if [[ "$PREVIOUS_SHA" == "$CURRENT_SHA" ]]; then
        log "本次部署 commit 未变化（$CURRENT_SHA），跳过"
        exit 0
    fi
    # git diff 需要两个 commit 都在本地。慢网下 PREVIOUS_SHA 一定在（它是部署前
    # 的 HEAD），CURRENT_SHA 也在（deploy.sh 刚 reset 到它）。
    if ! CHANGED=$(git diff --name-only "$PREVIOUS_SHA" "$CURRENT_SHA" -- src/collectors/ 2>/dev/null); then
        log "WARN: git diff 失败（commit 不可达？）—— 保守起见按有变更处理"
        CHANGED="(diff 失败)"
    fi
    if [[ -z "$CHANGED" ]]; then
        log "src/collectors/ 无变更（$PREVIOUS_SHA → $CURRENT_SHA），跳过重建"
        exit 0
    fi
    log "检测到 src/collectors/ 变更:"
    echo "$CHANGED" | sed 's/^/    /' | tee -a "$LOG_FILE"
else
    log "--force：跳过变更检测"
fi

cd "$COLLECTORS_DIR"

# ===== 2. 记录当前镜像（供人工回滚参考）=====
# 不做自动回滚：采集器不是关键路径（挂了只是资产同步停更，不影响告警/查询），
# 自动回滚镜像要维护 image 标签体系，收益不抵复杂度。这里把回滚所需信息打进
# 日志，人工一条命令就能回去。
OLD_IMAGES=$(docker compose images -q 2>/dev/null | tr '\n' ' ' || echo "")
log "当前镜像 ID: ${OLD_IMAGES:-（无）}"
log "人工回滚: cd $COLLECTORS_DIR && git checkout <旧sha> -- . && docker compose up -d --build"

# ===== 3. build =====
log "===== docker compose build ====="
if ! docker compose build 2>&1 | tail -30 | sed 's/^/    /' | tee -a "$LOG_FILE"; then
    log "ERROR: 镜像 build 失败 —— 现有容器未被触碰，仍在跑旧镜像"
    exit 1
fi
log "build 完成"

# ===== 4. 重建容器 =====
# up -d 只会重建镜像/配置有变化的 service，没变的原地不动。
log "===== docker compose up -d ====="
if ! docker compose up -d 2>&1 | sed 's/^/    /' | tee -a "$LOG_FILE"; then
    log "ERROR: docker compose up -d 失败"
    exit 1
fi

# ===== 5. 等健康 =====
# tplink 的 HEALTHCHECK 是 interval=60s + start-period=15s，首个结论最坏要
# ~75s；wazuh 是 interval=30s。所以这里给到 200s。
log "===== 等待容器健康（最多 ${HEALTH_WAIT_SECONDS}s）====="
SERVICES=$(docker compose config --services)
DEADLINE=$(( $(date +%s) + HEALTH_WAIT_SECONDS ))
FAILED=""

while :; do
    PENDING=""
    FAILED=""
    for svc in $SERVICES; do
        cid=$(docker compose ps -q "$svc" 2>/dev/null || echo "")
        if [[ -z "$cid" ]]; then
            FAILED="$FAILED $svc(未创建)"
            continue
        fi
        running=$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || echo "false")
        if [[ "$running" != "true" ]]; then
            FAILED="$FAILED $svc(未运行)"
            continue
        fi
        # 没配 healthcheck 的 service，Running 即视为通过
        health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo "none")
        case "$health" in
            healthy|none) ;;
            starting)     PENDING="$PENDING $svc" ;;
            *)            FAILED="$FAILED $svc($health)" ;;
        esac
    done

    if [[ -z "$PENDING" && -z "$FAILED" ]]; then
        log "全部服务健康: $(echo $SERVICES | tr '\n' ' ')"
        break
    fi
    if [[ $(date +%s) -ge $DEADLINE ]]; then
        log "ERROR: 超时。未通过:${FAILED:-无} 仍在 starting:${PENDING:-无}"
        for svc in $SERVICES; do
            log "--- $svc 最后 15 行日志 ---"
            docker compose logs --tail 15 "$svc" 2>&1 | sed 's/^/    /' | tee -a "$LOG_FILE" || true
        done
        exit 1
    fi
    sleep 5
done

# ===== 6. 事后核查：僵尸进程 =====
# init: true 生效的话，healthcheck 的 exec 子进程会被 tini 回收，这里应当是 0。
# 单独打出来是因为这个数字曾经涨到 233 而没人发现 —— 有个数字在日志里，
# 下次异常就能被看见。
for svc in $SERVICES; do
    cid=$(docker compose ps -q "$svc" 2>/dev/null || echo "")
    [[ -z "$cid" ]] && continue
    pid=$(docker inspect -f '{{.State.Pid}}' "$cid" 2>/dev/null || echo "")
    [[ -z "$pid" || "$pid" == "0" ]] && continue
    zcount=$(ps -eo ppid,stat --no-headers 2>/dev/null | awk -v p="$pid" '$1==p && $2 ~ /Z/' | wc -l | tr -d ' ')
    init_on=$(docker inspect -f '{{.HostConfig.Init}}' "$cid" 2>/dev/null || echo "?")
    log "$svc: PID=$pid init=$init_on 僵尸子进程=$zcount"
    if [[ "$zcount" -gt 0 ]]; then
        log "  WARN: 仍有僵尸子进程，确认 compose 的 init: true 是否生效"
    fi
done

log "====== 采集器部署成功: $CURRENT_SHA ======"
exit 0
