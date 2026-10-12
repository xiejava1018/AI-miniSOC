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

# 不在 Dockerfile 里写 HEALTHCHECK。历史版本每 60s 调 --test 模式
# 走 test_connection() 登录路由器，但 TP-Link 路由器自带防爆破节流（5 分钟
# 封禁），每分钟一次登录会被打为 401 触发路由器"错误密码登录"告警；同时
# 业务密码一换（生产已发生：102 容器内 ROUTER_PASSWORD 失配 4 天）就会
# 持续刷 401，刷出整页告警。健康度交给 compose 段的 healthcheck 段——
# 它只打 AI-miniSOC 的 /api/v1/health，不接触数据源。

ENTRYPOINT ["python", "-m", "tplink_collector"]
CMD ["--config", "/app/config.yaml"]
