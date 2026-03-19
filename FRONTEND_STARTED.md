## 🚀 AI-miniSOC 前后端已启动！

### 访问地址

**前端**: http://localhost:5173 (或 http://192.168.0.42:5173)
**后端**: http://localhost:8000
**API文档**: http://localhost:8000/docs

### ✅ 当前运行状态

| 服务 | 状态 | 地址 |
|------|------|------|
| **前端** | ✅ 运行中 | http://localhost:5173 |
| **后端** | ✅ 运行中 | http://localhost:8000 |
| **API代理** | ✅ 已配置 | /api/* → http://localhost:8000/api/v1/* |

### 📊 可用的API端点

```bash
# 资产管理
GET  /api/v1/assets/                    # �产列表
POST /api/v1/assets/sync/from-wazuh   # 从Wazuh同步资产

# 事件管理
GET  /api/v1/incidents/               # 事件列表
POST /api/v1/incidents/               # 创建事件

# 告警管理
GET  /api/v1/alerts/                   # 告警列表
GET  /api/v1/alerts/statistics       # 告警统计

# AI分析
POST /api/v1/ai/analyze-alert         # AI分析告警
POST /api/v1/ai/explain               # 解释日志
```

### 🎨 前端页面

- **概览仪表板**: http://localhost:5173/dashboard
- **资产管理**: http://localhost:5173/assets
- **事件管理**: http://localhost:5173/incidents
- **告警管理**: http://localhost:5173/alerts

### 🔧 测试API

```bash
# 测试后端健康检查
curl http://localhost:8000/health

# 测试资产API
curl http://localhost:8000/api/v1/assets/?limit=2

# 测试AI分析
curl -X POST http://localhost:8000/api/v1/ai/analyze-alert \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "test_001",
    "rule_level": 5,
    "rule_description": "SSH登录失败"
  }'
```

### 📝 注意事项

1. **前端代理**: 开发模式下，Vite会代理 /api/* 请求到后端
2. **CORS**: 后端已配置允许前端跨域访问
3. **热重载**: 前后端都支持代码修改后自动重载

### 🎯 下一步

现在可以：
1. 打开浏览器访问前端页面
2. 测试各个功能模块
3. 根据需要调整UI和功能

**前端已准备就绪！** 🎉
