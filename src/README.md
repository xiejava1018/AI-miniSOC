# AI-miniSOC

AI驱动的微型安全运营中心

## 快速开始

### 前置要求

- Node.js 18+
- Python 3.10+
- PostgreSQL 14+

### 安装

#### 1. 克隆项目
```bash
git clone <repository-url>
cd AI-miniSOC
```

#### 2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 填入真实配置
```

#### 3. 启动后端
```bash
cd src/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### 4. 启动前端
```bash
cd src/frontend
npm install
npm run dev
```

#### 5. 访问应用
- 前端: http://localhost:5173
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

## 项目结构

```
AI-miniSOC/
├── src/
│   ├── backend/       # FastAPI 后端
│   └── frontend/      # Vue.js 3 前端
├── configs/           # 配置文件
├── scripts/           # 工具脚本
├── docs/              # 文档
└── docker-compose.yml # Docker 编排
```

## 技术栈

### 后端
- FastAPI
- SQLAlchemy
- PostgreSQL
- 智谱AI (GLM)

### 前端
- Vue.js 3
- TypeScript
- Element Plus
- Pinia
- Vite

## 核心功能

### MVP v0.1
- ✅ 资产管理
- ✅ AI智能告警解释
- ✅ 事件工作流

### 计划中
- 自动漏洞扫描
- 自然语言查询
- 自动化响应
- 合规报告

## 文档

详细文档请查看 `docs/` 目录：
- [架构设计](docs/design/architecture.md)
- [产品愿景](docs/design/product-vision-and-technical-roadmap.md)
- [实施总结](docs/design/ai-minisoc-implementation-summary.md)

## 开发指南

详见：
- [后端开发指南](src/backend/README.md)
- [前端开发指南](src/frontend/README.md)

## 许可证

[待定]
