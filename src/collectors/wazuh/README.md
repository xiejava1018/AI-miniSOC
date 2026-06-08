# Wazuh Collector

Wazuh 数据采集器，从 Wazuh SIEM 采集资产、漏洞、基线数据并推送到 AI-miniSOC。

## 功能

- **资产采集**: 同步 Wazuh agents 到 AI-miniSOC 资产表
- **漏洞采集**: 同步 Vulnerability Detector 检测到的漏洞
- **基线采集**: 同步 SCA（Security Configuration Assessment）检查结果

## 安装

```bash
# 从本地安装
pip install -e ../../base
pip install -e .

# 或使用 pip（发布后）
pip install wazuh-collector
```

## 配置

创建配置文件 `config.yaml`：

```yaml
minisoc:
  url: http://192.168.0.40:8000
  api_key: ${MINISOC_API_KEY}

collect:
  interval: 300
  types:
    - asset
    - vulnerability
    - baseline

wazuh:
  url: https://192.168.0.40:55000
  user: ${WAZUH_USER:-wazuh-wui}
  password: ${WAZUH_PASSWORD}
  verify_ssl: false
```

设置环境变量：

```bash
export MINISOC_API_KEY="your-api-key"
export WAZUH_PASSWORD="your-password"
```

## 使用

### 命令行

```bash
# 测试连接
python -m wazuh_collector --test

# 单次采集
python -m wazuh_collector --once

# 定时采集（默认 5 分钟）
python -m wazuh_collector

# 自定义间隔（1 分钟）
python -m wazuh_collector --interval 60

# 指定采集类型
python -m wazuh_collector --types asset,vulnerability
```

### Docker

```bash
# 构建镜像
docker build -t wazuh-collector .

# 运行
docker run -d \
  -e MINISOC_API_KEY="your-key" \
  -e WAZUH_PASSWORD="your-password" \
  -v $(pwd)/config.yaml:/etc/wazuh-collector/config.yaml \
  wazuh-collector
```

### Docker Compose

```yaml
services:
  wazuh-collector:
    build: .
    environment:
      - MINISOC_API_KEY=${MINISOC_API_KEY}
      - WAZUH_PASSWORD=${WAZUH_PASSWORD}
    volumes:
      - ./config.yaml:/etc/wazuh-collector/config.yaml
```

## 数据映射

### 资产数据

| Wazuh 字段 | AI-miniSOC 字段 |
|-----------|----------------|
| id.ip | asset_ip |
| id.name | name |
| status | asset_status |
| os.name | os_name |
| os.version | os_version |

### 漏洞数据

| Wazuh 字段 | AI-miniSOC 字段 |
|-----------|----------------|
| cve.id | cve_id |
| severity | severity (映射) |
| condition.status | status |
| condition.version | affected_version |

### 基线数据

| Wazuh 字段 | AI-miniSOC 字段 |
|-----------|----------------|
| name | baseline_name |
| policy_id | source_id (部分) |
| pass | passed_checks |
| fail | failed_checks |
