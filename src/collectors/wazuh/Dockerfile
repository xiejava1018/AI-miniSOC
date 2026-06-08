FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制 collector-framework
COPY ../base /tmp/base
RUN pip install --no-cache-dir /tmp/base

# 复制项目文件
COPY pyproject.toml ./
COPY src ./src

# 安装本包及其依赖
RUN pip install --no-cache-dir -e .

# 复制配置
COPY config.yaml /etc/wazuh-collector/
COPY .env.example /etc/wazuh-collector/.env.example

# 创建非 root 用户
RUN useradd -m -u 1000 collector && \
    chown -R collector:collector /app /etc/wazuh-collector

USER collector

# 健康检查
HEALTHCHECK --interval=60s --timeout=15s --start-period=30s --retries=3 \
    CMD python -c "
import asyncio
import sys
sys.path.insert(0, '/app/src')
from wazuh_collector.collector import WazuhCollector
from collector_framework.config import CollectorConfig

async def test():
    cfg = CollectorConfig.from_yaml('/etc/wazuh-collector/config.yaml')
    c = WazuhCollector(cfg)
    try:
        result = await c.test_connection()
        sys.exit(0 if result else 1)
    except:
        sys.exit(1)
asyncio.run(test())
" || exit 1

# 默认命令
CMD ["python", "-m", "wazuh_collector", "--config", "/etc/wazuh-collector/config.yaml"]
