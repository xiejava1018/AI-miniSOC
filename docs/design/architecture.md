# AI-miniSOC 项目架构设计

## 1. 系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     AI-miniSOC Platform                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐   │
│  │   Dashboard   │  │  AI Analyzer  │  │ Alert Engine │   │
│  │   (前端界面)    │  │  (AI分析引擎)  │  │ (告警引擎)     │   │
│  └───────────────┘  └───────────────┘  └──────────────┘   │
│         │                   │                   │           │
│         └───────────────────┼───────────────────┘           │
│                             │                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API Gateway (REST/WebSocket)            │  │
│  └──────────────────────────────────────────────────────┘  │
│                             │                               │
│         ┌───────────────────┼───────────────────┐           │
│         │                   │                   │           │
│  ┌──────▼──────┐    ┌──────▼──────┐   ┌───────▼─────┐    │
│  │    Loki     │    │   Wazuh     │   │ OpenSearch  │    │
│  │  (日志存储)  │    │   (SIEM)     │   │  (搜索引擎)   │    │
│  └─────────────┘    └─────────────┘   └─────────────┘    │
│         │                   │                   │           │
│  ┌──────▼──────┐    ┌──────▼──────┐   ┌───────▼─────┐    │
│  │ Log Collector│   │  Filebeat   │   │  Metrics    │    │
│  │ (日志采集)    │   │  (日志转发)   │   │ (Prometheus)│    │
│  └─────────────┘    └─────────────┘   └─────────────┘    │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                      Data Sources                            │
│  Hosts │ Network │ Applications │ Security Tools             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
日志源 → 日志采集器 → Loki/Wazuh → AI分析 → 告警引擎 → 仪表板
  │                                                      │
  └──────────────────────────────────────────────────────┘
                     用户交互与响应
```

## 2. 核心组件设计

### 2.1 日志采集层

**组件**:
- Wazuh Agent (主机日志)
- Filebeat (应用日志)
- Otelp (OTLP协议)
- Custom Collector (自定义采集器)

**数据格式**:
```json
{
  "timestamp": "2026-03-09T09:00:00Z",
  "level": "info",
  "host": "192.168.0.2",
  "service": "nginx",
  "message": "...",
  "labels": {
    "env": "prod",
    "datacenter": "dc1"
  }
}
```

### 2.2 存储层

**Loki**:
- 索引: 标签索引
- 存储: 文件系统 (/data/loki)
- 保留期: 7天
- 压缩: Snappy

**Wazuh/OpenSearch**:
- 索引: 按日期分片
- 保留期: 30天
- 副本: 1

### 2.3 分析层

**AI Analyzer**:
```python
class AIAnalyzer:
    def analyze_log(self, log_entry):
        # 日志解析
        # 异常检测
        # 威胁识别
        # 关联分析
        pass

    def detect_anomaly(self, logs):
        # 统计分析
        # 机器学习模型
        # 规则引擎
        pass
```

**功能**:
- 日志模式识别
- 异常行为检测
- 威胁情报关联
- 风险评分

### 2.4 告警引擎

**告警级别**:
- P0: 严重 (立即处理)
- P1: 高 (1小时内)
- P2: 中 (24小时内)
- P3: 低 ( informational)

**告警规则**:
```yaml
rules:
  - name: "多次登录失败"
    condition: "failed_login > 5 in 5m"
    level: "P1"
    action: "notify"
```

**通知渠道**:
- 邮件
- 钉钉
- 微信
- Webhook

### 2.5 可视化层

**Grafana仪表板**:
- 系统概览
- 威胁态势
- 告警统计
- 性能指标

**自定义Dashboard**:
- 实时日志流
- 拓扑视图
- 攻击链分析
- 趋势预测

## 3. 技术栈

### 3.1 后端
- **语言**: Python 3.10+, Node.js 18+
- **框架**: FastAPI, Express
- **数据库**: PostgreSQL (配置), Redis (缓存)

### 3.2 前端
- **框架**: React 18, TypeScript
- **UI库**: Ant Design, D3.js
- **状态管理**: Zustand
- **图表**: ECharts, Grafana

### 3.3 AI/ML
- **框架**: PyTorch, scikit-learn
- **NLP**: Transformers, OpenAI API
- **时序**: Prophet, statsmodels

### 3.4 基础设施
- **容器**: Docker, Docker Compose
- **编排**: Kubernetes (可选)
- **监控**: Prometheus, Grafana
- **日志**: Loki, Wazuh

## 4. 数据模型

### 4.1 告警数据模型
```json
{
  "id": "alert-123456",
  "timestamp": "2026-03-09T09:00:00Z",
  "level": "P1",
  "title": "多次登录失败",
  "description": "...",
  "source": {
    "host": "192.168.0.2",
    "service": "ssh",
    "log_id": "..."
  },
  "status": "open",
  "assigned_to": "xiejava",
  "tags": ["brute-force", "ssh"],
  "metrics": {
    "failed_count": 10,
    "time_window": "5m"
  }
}
```

### 4.2 日志数据模型
```json
{
  "id": "log-789012",
  "timestamp": "2026-03-09T09:00:00Z",
  "level": "warning",
  "host": "192.168.0.2",
  "service": "nginx",
  "message": "...",
  "labels": {
    "env": "prod",
    "region": "cn"
  },
  "parsed": {
    "method": "GET",
    "path": "/api/users",
    "status": 404,
    "response_time": 0.5
  }
}
```

### 4.3 威胁情报模型
```json
{
  "indicator": "192.168.0.100",
  "type": "ip",
  "confidence": 85,
  "source": "threat_feed",
  "first_seen": "2026-03-01T00:00:00Z",
  "last_seen": "2026-03-09T09:00:00Z",
  "tags": ["malware", "botnet"],
  "description": "Known malicious IP"
}
```

## 5. 部署架构

### 5.1 开发环境
```
localhost (Docker Compose)
├── loki
├── grafana
├── wazuh-indexer
├── wazuh-server
├── wazuh-dashboard
└── ai-analyzer
```

### 5.2 生产环境
```
192.168.0.30 (主服务器)
├── Loki (日志存储)
├── Grafana (可视化)
├── Wazuh (SIEM)
└── OpenSearch (搜索引擎)

监控主机 (192.168.0.*)
├── Wazuh Agent
└── Log Collector
```

## 6. 安全设计

### 6.1 认证与授权
- JWT Token认证
- RBAC权限控制
- API密钥管理

### 6.2 数据安全
- 传输加密 (HTTPS/TLS)
- 敏感数据加密存储
- 日志脱敏

### 6.3 审计
- 操作日志记录
- 访问审计
- 变更追踪

## 7. 性能优化

### 7.1 日志采集
- 批量传输
- 压缩
- 异步处理

### 7.2 查询优化
- 索引优化
- 缓存 (Redis)
- 分页查询
- 并行处理

### 7.3 存储优化
- 定期清理过期数据
- 冷热数据分离
- 压缩归档

## 8. 扩展性设计

### 8.1 水平扩展
- 无状态API服务
- 负载均衡
- 分布式存储

### 8.2 插件机制
- 自定义解析器
- 自定义告警规则
- 自定义分析器

---

**版本**: v1.0
**最后更新**: 2026-03-09
