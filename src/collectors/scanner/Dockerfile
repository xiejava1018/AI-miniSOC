# scanner-collector Dockerfile（P3/F-S2）
#
# Phase 1：python:3.13-slim + apt install nmap
#   理由：slim 镜像小（~150MB）+ nmap 已包含
#         容器内仅跑 nmap，Kali 镜像特性（masscan/ncat/NSE 全套）暂不需要
# Phase 4：升级到 kalilinux/kali-rolling 或 instrumentisto/nmap 启用 NSE
#
# 设计：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §10.1

FROM python:3.13-slim

# 安装 nmap + curl（健康检查需要）
# apt-get update 在 cache 失效时会失败，重试一次
RUN apt-get update || (sleep 5 && apt-get update) \
    && apt-get install -y --no-install-recommends \
        nmap \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# 安全：非 root 运行（nmap 需要 raw socket，root 才能发包；Phase 2 再考虑非 root + cap_net_raw）
# Phase 1 暂保留 root；后续用 setcap 给 Python 二进制 NET_RAW 能力
# USER scanner
WORKDIR /app

# 先装依赖（Docker 层缓存）
COPY base/ /tmp/base/
COPY scanner/pyproject.toml /app/pyproject.toml

# editable 装：base + scanner 本地
RUN pip install --no-cache-dir -e /tmp/base/ && pip install --no-cache-dir -e /app

# 装包代码
COPY scanner/scanner_collector/ /app/scanner_collector/
COPY scanner/run_scanner.py /app/run_scanner.py

# env defaults（docker-compose 可覆盖）
ENV SCAN_PUBLIC_TARGETS=""
ENV MINISOC_URL="http://host.docker.internal:8000"
ENV NMAP_BINARY="/usr/bin/nmap"
ENV NMAP_TIMEOUT=300
ENV NMAP_MAX_RATE=100
ENV SCANNER_LOG_LEVEL="INFO"

# tini 收尸（避免僵尸进程：CLAUDE.md P4 教训）
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/app/run_scanner.py"]

# 默认 --once（生产 cron 触发；--loop 给开发调试用）
CMD ["--once"]