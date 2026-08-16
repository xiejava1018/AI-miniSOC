#!/bin/bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend
# P3-T4（数据可靠性）：后台调度器为进程内单例，须单 worker 部署。
# 多 worker 会导致 browsing/alert/KEV 调度重复执行与缓存漂移（详见
# app/services/single_worker_guard.py）。生产部署请保持 --workers 1 或显式传入 -w 1。
UVICORN_WORKERS="${UVICORN_WORKERS:-1}" \
nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --workers 1 > /tmp/backend.log 2>&1 &
echo "Backend started with PID: $!"
