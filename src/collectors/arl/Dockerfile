# ---- 构建阶段 ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY base/ /build/base/
RUN pip install --no-cache-dir /build/base

COPY arl/ /build/arl/
RUN pip install --no-cache-dir /build/arl

# ---- 运行阶段 ----
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# 不在 Dockerfile 里写 HEALTHCHECK（照 tplink 决策）：历史教训——HEALTHCHECK
# 定期调 --test 会刷外部系统（ARL 登录会话/审计日志），凭据失效后持续失败
# 刷屏。健康度交给 compose 的 healthcheck 段——只打 AI-miniSOC /api/v1/health，
# 不接触 ARL 数据源。

ENTRYPOINT ["python", "-m", "arl_collector"]
CMD []
