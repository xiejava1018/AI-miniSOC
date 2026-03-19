# AI-miniSOC Frontend

Vue.js 3 + TypeScript 前端应用

## 快速开始

### 1. 安装依赖
```bash
npm install
```

### 2. 启动开发服务器
```bash
npm run dev
```

### 3. 构建生产版本
```bash
npm run build
```

## 项目结构

```
frontend/
├── src/
│   ├── api/           # API 客户端
│   ├── components/    # Vue 组件
│   ├── router/        # 路由配置
│   ├── stores/        # Pinia 状态管理
│   ├── utils/         # 工具函数
│   ├── views/         # 页面组件
│   ├── App.vue        # 根组件
│   └── main.ts        # 应用入口
├── public/            # 静态资源
├── index.html         # HTML 模板
├── package.json       # 依赖配置
└── vite.config.ts     # Vite 配置
```

## 技术栈

- **框架**: Vue 3 (Composition API)
- **语言**: TypeScript
- **构建工具**: Vite
- **UI 组件**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **HTTP 客户端**: Fetch API

## 页面

- `/dashboard` - 概览仪表板
- `/assets` - 资产管理
- `/assets/:id` - 资产详情
- `/incidents` - 事件管理
- `/incidents/:id` - 事件详情
- `/alerts` - 告警管理

## 开发指南

### API 调用
```typescript
import { assetsApi } from '@/api'

// 获取资产列表
const assets = await assetsApi.list({ skip: 0, limit: 100 })

// 创建资产
await assetsApi.create({ name: '服务器', asset_ip: '192.168.1.1' })
```

### 状态管理
```typescript
import { useAssetStore } from '@/stores/assets'

const assetStore = useAssetStore()
await assetStore.fetchAssets()
```

### 路由导航
```typescript
import { useRouter } from 'vue-router'

const router = useRouter()
router.push('/assets')
```

## 环境变量

创建 `.env.local` 文件：
```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```
