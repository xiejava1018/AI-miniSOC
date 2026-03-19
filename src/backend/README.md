# AI-miniSOC Backend

FastAPI 后端服务，提供资产管理、事件工作流、AI分析等API。

## 快速开始

### 1. 安装依赖
```bash
cd src/backend
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
# 在项目根目录创建 .env 文件
cp ../../.env.example .env
# 编辑 .env 填入真实配置
```

### 3. 运行开发服务器
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问 API 文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── api/           # API 路由
│   ├── core/          # 核心配置（数据库、认证、设置）
│   ├── models/        # SQLAlchemy 数据库模型
│   ├── schemas/       # Pydantic 数据模式
│   └── services/      # 业务逻辑服务
├── tests/             # 测试
├── main.py            # 应用入口
└── requirements.txt   # Python 依赖
```

## API 端点

### 资产管理
- `GET /api/v1/assets` - 资产列表
- `GET /api/v1/assets/{id}` - 资产详情
- `POST /api/v1/assets` - 创建资产
- `PUT /api/v1/assets/{id}` - 更新资产
- `DELETE /api/v1/assets/{id}` - 删除资产

### 事件管理
- `GET /api/v1/incidents` - 事件列表
- `GET /api/v1/incidents/{id}` - 事件详情
- `POST /api/v1/incidents` - 创建事件
- `PUT /api/v1/incidents/{id}` - 更新事件

### 告警管理 (Wazuh)
- `GET /api/v1/alerts` - 告警列表
- `GET /api/v1/alerts/{id}` - 告警详情
- `POST /api/v1/alerts/{id}/create-incident` - 从告警创建事件

### AI 分析 (智谱AI)
- `POST /api/v1/ai/analyze-alert` - AI分析告警
- `GET /api/v1/ai/analysis/{id}` - 获取分析结果

## 开发指南

### 数据库模型
在 `app/models/` 中定义 SQLAlchemy 模型

### API 开发
1. 在 `app/api/` 中创建新的路由文件
2. 在 `app/schemas/` 中定义请求/响应模式
3. 在 `app/services/` 中实现业务逻辑
4. 在 `app/api/__init__.py` 中注册路由

### 环境变量
主要配置项（见 .env.example）：
- `DB_HOST`, `DB_PASSWORD` - 数据库连接
- `GLM_API_KEY` - 智谱AI API密钥
- `WAZUH_API_URL`, `WAZUH_API_USERNAME`, `WAZUH_API_PASSWORD` - Wazuh配置
- `JWT_SECRET_KEY` - JWT密钥

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_assets.py

# 查看测试覆盖率
pytest --cov=app tests/
```
