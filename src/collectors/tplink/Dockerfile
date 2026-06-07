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

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD python -m tplink_collector --test || exit 1

ENTRYPOINT ["python", "-m", "tplink_collector"]
CMD ["--config", "/app/config.yaml"]
