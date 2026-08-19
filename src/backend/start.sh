#!/bin/bash
###############################################################################
# ⚠️ 已废弃（2026-08-19）— 仅供应急参考，请勿日常使用
#
# 生产环境后端现在由 systemd 管理（见 deploy/aisoc-backend.service）：
#   启动/停止/重启:  sudo systemctl start|stop|restart aisoc-backend
#   看状态:          systemctl status aisoc-backend
#   看日志:          tail -f /var/log/aisoc/backend.log
#                    sudo journalctl -u aisoc-backend -f
#
# 部署由 CI/CD 自动完成（push master → CI 全绿 → self-hosted runner
# 跑 deploy/deploy.sh，详见 docs/development/cicd.md）。
# 手动部署指定 commit:  bash deploy/deploy.sh <commit_sha>
#
# 本脚本的问题（被 systemd 取代的原因）：
#   - nohup 进程崩了不自动拉起、服务器重启不自启
#   - 带了 --reload（dev 参数，生产不该有）
#   - 日志在 /tmp（重启丢失）
#
# 应急用法（systemd 彻底坏掉时）：
#   UVICORN_WORKERS=1 nohup ./venv/bin/python -m uvicorn main:app \
#     --host 0.0.0.0 --port 8000 --workers 1 > /tmp/backend.log 2>&1 &
###############################################################################

cd /home/xiejava/AIproject/AI-miniSOC/src/backend
# P3-T4（数据可靠性）：后台调度器为进程内单例，须单 worker 部署。
# 多 worker 会导致 browsing/alert/KEV 调度重复执行与缓存漂移（详见
# app/services/single_worker_guard.py）。生产部署请保持 --workers 1 或显式传入 -w 1。
UVICORN_WORKERS="${UVICORN_WORKERS:-1}" \
nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --workers 1 > /tmp/backend.log 2>&1 &
echo "⚠️  start.sh 已废弃（用 systemd）；应急模式启动 PID: $!"