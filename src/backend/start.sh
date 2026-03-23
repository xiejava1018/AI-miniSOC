#!/bin/bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend
nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > /tmp/backend.log 2>&1 &
echo "Backend started with PID: $!"
