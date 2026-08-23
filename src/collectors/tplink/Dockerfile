# ---- 构建阶段 ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY base/ /build/base/
RUN pip install --no-cache-dir /build/base

COPY tplink/ /build/tplink/
RUN pip install --no-cache-dir /build/tplink

# ---- 运行阶段 ----
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

COPY tplink/config.example.yaml /app/config.yaml

# timeout 从 5s 提到 15s：一轮自检要跟路由器登录 + 后端 /health 两次网络往返，
# 实测 p50 约 1s，但路由器偶尔反应慢时会超 5s 被 docker SIGKILL。被 kill 的探针
# 既会把容器误判为 unhealthy，又会留下无人回收的子进程（配合 compose 的
# init: true 一起治）。start-period 避开启动瞬间的假告警。
HEALTHCHECK --interval=60s --timeout=15s --start-period=15s --retries=3 \
    CMD python -m tplink_collector --test || exit 1

ENTRYPOINT ["python", "-m", "tplink_collector"]
CMD ["--config", "/app/config.yaml"]
