# Wazuh 采集器集成文档

## 概述

Wazuh 采集器已按照《采集器集成架构设计》完成重构，实现了从 Wazuh SIEM 采集资产、漏洞、基线数据并推送到 AI-miniSOC。

## 目录结构

```
src/collectors/wazuh/
├── src/wazuh_collector/
│   ├── __init__.py          # 包初始化
│   ├── __main__.py          # 入口脚本（CLI）
│   ├── collector.py         # WazuhCollector 主类
│   ├── wazuh_client.py      # Wazuh API 客户端
│   └── transformers.py      # 数据转换器
├── config.yaml              # 配置文件
├── .env.example             # 环境变量模板
├── Dockerfile               # Docker 镜像构建
├── pyproject.toml           # 项目配置
├── README.md                # 使用文档
└── test_local.py            # 本地测试脚本
```

## 架构关系

```
┌─────────────────┐
│ Wazuh SIEM      │
│ 192.168.0.40:55000│
└────────┬────────┘
         │ API (JWT)
         ▼
┌─────────────────┐
│ WazuhCollector  │
│  - BaseCollector│
│  - MiniSOCClient│
└────────┬────────┘
         │ POST /api/v1/data/sync
         ▼
┌─────────────────┐
│ AI-miniSOC      │
│ /api/v1/data/sync│
└─────────────────┘
```

## 支持的数据类型

| 类型 | DataType | 说明 | Handler |
|------|----------|------|---------|
| 资产 | asset | Wazuh agents | AssetSyncHandler |
| 漏洞 | vulnerability | Vulnerability Detector | VulnerabilitySyncHandler |
| 基线 | baseline | SCA 检查结果 | BaselineSyncHandler |

## 部署方式

### 方式 1: Docker Compose（推荐）

1. 配置环境变量:
```bash
cd src/collectors
cp .env.example .env
# 编辑 .env 填入实际凭证
```

2. 启动服务:
```bash
docker-compose up -d wazuh-collector
```

3. 查看日志:
```bash
docker-compose logs -f wazuh-collector
```

### 方式 2: Docker 独立运行

```bash
cd src/collectors/wazuh

# 构建镜像
docker build -t wazuh-collector .

# 运行容器
docker run -d \
  -e MINISOC_API_KEY="your-key" \
  -e WAZUH_PASSWORD="your-password" \
  -v $(pwd)/config.yaml:/etc/wazuh-collector/config.yaml \
  --name wazuh-collector \
  wazuh-collector
```

### 方式 3: 本地 Python 环境

```bash
cd src/collectors/wazuh

# 安装依赖
pip install -e ../../base
pip install -e .

# 运行
python -m wazuh_collector --config config.yaml
```

## 配置说明

### config.yaml

```yaml
minisoc:
  url: http://192.168.0.40:8000      # AI-miniSOC 地址
  api_key: ${MINISOC_API_KEY}         # API Key（环境变量）

collect:
  interval: 300                       # 采集间隔（秒）
  types:                              # 采集类型
    - asset
    - vulnerability
    - baseline

wazuh:
  url: https://192.168.0.40:55000     # Wazuh API 地址
  user: ${WAZUH_USER}                 # Wazuh 用户名
  password: ${WAZUH_PASSWORD}          # Wazuh 密码
  verify_ssl: false                   # SSL 验证
```

## 命令行参数

```bash
# 测试连接
python -m wazuh_collector --test

# 单次采集
python -m wazuh_collector --once

# 自定义间隔（1 分钟）
python -m wazuh_collector --interval 60

# 指定采集类型
python -m wazuh_collector --types asset,vulnerability
```

## 数据映射

### 资产数据

| Wazuh Agent | AI-miniSOC 资产 |
|-------------|---------------|
| id.ip | asset_ip |
| id.name | name |
| id.id | wazuh_agent_id |
| status | asset_status (active→online) |
| os.name | os_name |
| os.version | os_version |

### 漏洞数据

| Wazuh Vulnerability | AI-miniSOC 漏洞 |
|---------------------|----------------|
| cve.id | cve_id |
| severity | severity (映射) |
| condition.status | status |
| condition.version | affected_version |

### 基线数据

| Wazuh SCA | AI-miniSOC 基线 |
|-----------|----------------|
| name | baseline_name |
| policy_id | source_id (部分) |
| pass | passed_checks |
| fail | failed_checks |

## 健康检查

Docker 容器内置健康检查，每 30 秒检查一次：

1. Wazuh API 连接测试
2. AI-miniSOC 连接测试

查看健康状态:
```bash
docker inspect wazuh-collector | jq '.[0].State.Health'
```

## 日志

日志级别: INFO
格式: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

查看日志:
```bash
# Docker
docker logs wazuh-collector

# Docker Compose
docker-compose logs wazuh-collector
```

## 故障排查

### 问题: 无法连接 Wazuh API

检查项:
- Wazuh URL 是否正确
- 用户名密码是否正确
- 网络是否可达

```bash
# 测试连接
curl -k -u wazuh-wui:password https://192.168.0.40:55000/
```

### 问题: 同步失败

检查项:
- AI-miniSOC 是否运行
- API Key 是否正确
- /api/v1/data/sync 端点是否可访问

```bash
# 测试同步
curl -X POST http://192.168.0.40:8000/api/v1/data/sync \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"source":"test","data_type":"asset","items":[]}'
```

### 问题: Docker 构建失败

检查项:
- Dockerfile 中的路径引用是否正确
- base 框架是否可访问

```bash
# 手动构建测试
cd src/collectors/wazuh
docker build -t wazuh-collector --no-cache .
```

## 与旧代码的对比

### 旧实现 (wazuh_agent_sync.py)

- 作为后台服务直接调用
- 通过 `/sync/wazuh-agents` 端点手动触发
- 仅支持资产数据
- 同步逻辑内嵌在主服务中

### 新实现 (WazuhCollector)

- 继承 `BaseCollector` 抽象类
- 独立 Docker 容器运行
- 支持资产、漏洞、基线三种数据类型
- 通过 `MiniSOCClient` 推送数据
- 支持定时采集

## 下一步

1. **实现 Nmap 采集器**（Phase 4）
   - 端口扫描数据采集
   - 与资产关联

2. **实现调度机制**
   - Kubernetes CronJob
   - 或独立调度器服务

3. **监控和告警**
   - Prometheus 指标
   - 采集失败告警

## 参考

- [采集器集成架构设计](../../../docs/design/2026-06-07-collector-integration-architecture.md)
- [Wazuh API 文档](https://documentation.wazuh.com/current/user-manual/wazuh-api/index.html)
