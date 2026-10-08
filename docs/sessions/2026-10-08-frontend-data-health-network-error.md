# 2026-10-08 前端 data-health "网络错误" 三层修复

**状态**: ✅ 已修复 commit 028bb80
**关联**: CLAUDE.md §4.10（后端冷启动 8s+）

---

## 0. 触发

用户报：本地 `http://localhost:5173/#/ops/data-health` 报"网络错误"——但
102 生产 `http://192.168.0.102:8080/#/ops/data-health` 正常。后端代码、采集器、
数据库都相同。

## 1. 现象 + 排查

### 1.1 浏览器控制台错误

```
error.ts:89 [HTTP Request Error] {
  message: 'timeout of 15000ms exceeded',
  code: 'ECONNABORTED',
  url: '/api/v1/data-health',
  method: 'get',
  timestamp: '2026-10-08T15:05:56.242Z'
}
error.ts:120 [HTTP Error] {
  code: 400, message: '网络错误', data: undefined,
  url: '/api/v1/data-health', ...
}
```

**`code: 'ECONNABORTED'`**——是 axios 超时（不是连接拒绝/网络断开）。但 error.ts
把 ECONNABORTED 和 `!error.response` 一起归为"网络错误"——**误报**。

### 1.2 curl 旁路对照

```bash
# 走 vite proxy（127.0.0.1:5173 修后）
curl http://localhost:5173/api/v1/data-health    # HTTP 200, 0.14s

# 直打 8000
curl http://127.0.0.1:8000/api/v1/data-health   # HTTP 200, 0.003s

# 走 IPv6 localhost
curl http://localhost:8000/api/v1/data-health   # HTTP 000, 5s 超时
```

**关键差异**：
- `localhost` 在 Mac 上默认解析为 IPv6 `::1`
- uvicorn 监听 `0.0.0.0`（IPv4 only）——不接受 IPv6 连接
- vite proxy 用 `localhost:8000` 作为 target → 解析到 `::1:8000` → ECONNREFUSED

## 2. 三层根因 + 修复

### 2.1 vite proxy 走 IPv6 失败（最底）

`src/frontend/.env.development`：
```diff
- VITE_API_PROXY_URL=http://localhost:8000
+ VITE_API_PROXY_URL=http://127.0.0.1:8000
```

**但** `.env.development` 在 `.gitignore` 里（`.env.*`）——其他开发者 clone
代码后还是会遇到这个坑。所以**把默认值写在 `vite.config.ts` 代码层**：

```typescript
// vite.config.ts
const VITE_API_PROXY_URL = env.VITE_API_PROXY_URL || 'http://127.0.0.1:8000'
```

这样：
- 默认 `127.0.0.1`（IPv4 明确，绕开 Mac 双栈坑）
- `.env` 可以覆盖（生产/特殊环境）
- 任何开发者 clone 后不用改 `.env` 就能直接跑

### 2.2 axios timeout 15s 覆盖不了冷启动

`src/utils/http/index.ts`：
```diff
- const REQUEST_TIMEOUT = 15000
+ const REQUEST_TIMEOUT = 30000
```

`/api/v1/data-health` 第一次冷启动 = uvicorn lifespan（8s+）+ DB pool 预热
（3-5s）+ `AssetReconciliationService.summary()` JOIN 编译（10-15s）= 20-30s。
稳态后 ~3ms。

CLAUDE.md §4.10 已经提了"冷启动 8s+"——但 data-health 这个端点首次聚合
三表（source_health + 死信 + 对账差异）+ 4 次 scanner count，实测 20-30s。
**15s 不够**。

### 2.3 ECONNABORTED 被误报为"网络错误"

`src/utils/http/error.ts`：
```diff
+ if (error.code === 'ECONNABORTED') {
+   // axios timeout：不要误报为"网络错误"，后端可能正在冷启动/重查询
+   const httpError = new HttpError(
+     '请求超时，后端响应过慢或冷启动中，请重试',
+     ApiStatus.error,
+     ...
+   )
+   throw httpError
+ }
+
  if (!error.response) {
-   const httpError = new HttpError('网络错误', ApiStatus.error, ...)
+   const httpError = new HttpError('网络错误，请检查后端连接', ApiStatus.error, ...)
    throw httpError
  }
```

区分：
- `ECONNABORTED`（axios timeout）→ "请求超时，后端响应过慢或冷启动中，请重试"
- `!error.response`（真断网/CORS/DNS）→ "网络错误，请检查后端连接"

让用户能区分"后端慢"和"真连不上"。

## 3. 为什么 8080 没问题 5173 有问题

| 维度 | `http://192.168.0.102:8080`（生产） | `http://localhost:5173`（开发） |
|---|---|---|
| 前端 dist | nginx 静态文件 | vite dev server（HMR） |
| API 路径 | nginx `proxy_pass /api` → 102:8000 | vite proxy `/api` → 127.0.0.1:8000 |
| 后端 | 102 systemd 持续跑（不冷启动） | Mac 本地 uvicorn `--reload`（**冷启动 8-30s**） |
| 第一次响应 | 50ms | 8-30s（uvicorn lifespan + DB pool + 业务冷启动） |
| 稳态 | 50ms | 4ms |
| axios timeout | 15s → 30s | 15s → 30s |
| ECONNABORTED 显示 | "网络错误" → "请求超时..." | "网络错误" → "请求超时..." |

**生产 8080 不冷启动**——systemd 拉起的 uvicorn 持续在跑，nginx 转发立即响应。
**开发 5173 冷启动**——Mac 本地 uvicorn 是手工 `npm run dev` 起的，每次重启
后第一次请求要 8-30s 拉 lifespan + DB pool + 业务聚合。

## 4. 教训

- **本地双栈解析坑**——`localhost` 在现代 Mac 默认 IPv6，后端 IPv4 only 时必踩。
  任何本机代理配置（vite proxy / nginx / caddy）都用 `127.0.0.1` 明确 IPv4
- **axios timeout 跟后端冷启动不匹配**——CLAUDE.md §4.10 说 8s+，但**单个
  端点首次聚合**能 20-30s。timeout 应该 ≥ 已知最慢端点稳态冷启动 + 50% buffer
- **error 分类不能太粗暴**——`!error.response` 把 timeout / ECONNREFUSED /
  DNS 失败 / CORS 拦截全归一类，UI 无法给用户有用信息
- **默认值放代码层 vs .env 层**——容易踩坑的环境差异（如 localhost IPv6）
  应该写在 `vite.config.ts` 默认值里，不能依赖 .env（不入库）
