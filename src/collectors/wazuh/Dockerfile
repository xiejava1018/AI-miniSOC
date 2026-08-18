FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制 collector-framework
COPY base /tmp/base
RUN pip install --no-cache-dir /tmp/base

# 复制项目文件
COPY wazuh/pyproject.toml ./
COPY wazuh/src ./src

# 安装本包及其依赖
RUN pip install --no-cache-dir -e .

# 复制配置
COPY wazuh/config.yaml /etc/wazuh-collector/

# 创建非 root 用户
RUN useradd -m -u 1000 collector && \
    chown -R collector:collector /app /etc/wazuh-collector

USER collector


# 默认命令
CMD ["python", "-m", "wazuh_collector", "--config", "/etc/wazuh-collector/config.yaml"]
