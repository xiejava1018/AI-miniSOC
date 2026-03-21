# Phase 3: 动态菜单加载实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现基于用户角色的动态菜单加载，前端根据后端返回的菜单权限动态渲染侧边栏

**Architecture:**
- 后端：修改认证API返回用户菜单树
- 前端：修改auth store保存菜单，App.vue动态渲染，路由守卫权限检查
- 权限流程：登录 → 获取用户菜单 → 前端缓存 → 动态渲染 → 访问验证

**Dependencies:**
- ✅ Phase 1 (角色管理) 已完成
- ✅ Phase 2 (菜单管理) 已完成

---

## Task 1: 修改后端认证API返回菜单

**Files:**
- Modify: `src/backend/app/api/auth.py`
- Modify: `src/backend/app/models/user.py` (添加get_user_menus方法)

- [ ] **Step 1: 在User模型添加辅助方法**

```python
# src/backend/app/models/user.py
def get_user_menus(self) -> List[Menu]:
    """获取用户有权访问的菜单"""
    if not self.role or not self.role.menus:
        return []
    return sorted(self.role.menus, key=lambda m: m.sort_order or 0)
```

- [ ] **Step 2: 修改登录API返回菜单**

在 `auth.py` 的 `/login` 端点，返回时添加：
```python
# 获取用户菜单
user_menus = current_user.get_user_menus()
menu_tree = build_menu_tree_from_list(user_menus)

return {
    "access_token": access_token,
    "refresh_token": refresh_token,
    "user": UserResponse.model_validate(current_user),
    "menus": menu_tree  # 新增
}
```

- [ ] **Step 3: 修改/me端点返回菜单**

同样在 `/me` 端点添加菜单返回

---

## Task 2: 前端 - 修改Auth Store保存菜单

**Files:**
- Modify: `src/frontend/src/stores/auth.ts`

- [ ] **Step 1: 添加菜单状态**

```typescript
// 添加到 auth store
const menus = ref<MenuItem[]>([])

interface MenuItem {
  id: number
  parent_id?: number
  name: string
  path: string | null
  icon: string
  sort_order: number
  is_visible: boolean
  children?: MenuItem[]
}
```

- [ ] **Step 2: 修改login函数保存菜单**

```typescript
async function login(credentials: { username: string; password: string }) {
  const response = await api.login(credentials)
  token.value = response.access_token
  user.value = response.user
  menus.value = response.menus  // 新增

  localStorage.setItem('menus', JSON.stringify(response.menus))
}
```

- [ ] **Step 3: 添加fetchCurrentUser函数**

```typescript
async function fetchCurrentUser() {
  const response = await api.getCurrentUser()
  user.value = response.user
  menus.value = response.menus
  localStorage.setItem('menus', JSON.stringify(response.menus))
}
```

---

## Task 3: 前端 - 修改App.vue动态渲染菜单

**Files:**
- Modify: `src/frontend/src/App.vue`

- [ ] **Step 1: 删除硬编码菜单**

删除现有的硬编码menuItems数组

- [ ] **Step 2: 使用authStore.menus动态渲染**

```vue
<template>
  <aside class="sidebar" v-if="authStore.isAuthenticated">
    <nav class="sidebar-nav">
      <template v-for="item in authStore.menus" :key="item.id">
        <!-- 有子菜单 -->
        <div v-if="item.children && item.children.length > 0" class="nav-group">
          <div class="nav-group-title">
            <component :is="item.icon" class="nav-icon" />
            <span class="nav-label">{{ item.name }}</span>
          </div>
          <router-link
            v-for="child in item.children"
            :key="child.id"
            :to="child.path"
            class="nav-item nav-child"
          >
            <component :is="child.icon" class="nav-icon" />
            <span class="nav-label">{{ child.name }}</span>
          </router-link>
        </div>
        <!-- 无子菜单 -->
        <router-link
          v-else-if="item.path"
          :to="item.path"
          class="nav-item"
        >
          <component :is="item.icon" class="nav-icon" />
          <span class="nav-label">{{ item.name }}</span>
        </router-link>
      </template>
    </nav>
  </aside>
</template>
```

- [ ] **Step 3: 添加图标映射**

```typescript
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
const iconMap = ref<Record<string, any>>({})

onMounted(() => {
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    iconMap.value[key] = markRaw(component)
  }
})
```

---

## Task 4: 增强路由守卫权限检查

**Files:**
- Modify: `src/frontend/src/router/index.ts`

- [ ] **Step 1: 添加菜单权限检查函数**

```typescript
function checkMenuPermission(menus: MenuItem[], path: string): boolean {
  for (const menu of menus) {
    if (menu.path === path) return true
    if (menu.children) {
      if (checkMenuPermission(menu.children, path)) return true
    }
  }
  return false
}
```

- [ ] **Step 2: 修改beforeEach添加权限检查**

```typescript
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 检查认证
  if (to.meta.requiresAuth !== false && !authStore.isAuthenticated) {
    return next('/login')
  }

  // 检查菜单权限
  if (authStore.isAuthenticated && to.path !== '/login') {
    const hasPermission = checkMenuPermission(authStore.menus, to.path)
    if (!hasPermission) {
      return next('/403')
    }
  }

  next()
})
```

---

## Task 5: 初始化角色菜单权限

**Files:**
- Create: `src/backend/scripts/init_role_menus.sql`

- [ ] **Step 1: 创建初始化SQL**

```sql
-- 管理员拥有所有菜单
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT (SELECT id FROM soc_roles WHERE code='admin'), id
FROM soc_menus
ON CONFLICT DO NOTHING;

-- 普通用户拥有业务菜单（不含系统管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT (SELECT id FROM soc_roles WHERE code='user'), id
FROM soc_menus
WHERE path NOT LIKE '/system%' OR path IS NULL OR path = ''
ON CONFLICT DO NOTHING;

-- 只读用户仅有查看权限
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT (SELECT id FROM soc_roles WHERE code='readonly'), id
FROM soc_menus
WHERE path IN ('/dashboard', '/assets', '/incidents', '/alerts')
ON CONFLICT DO NOTHING;
```

---

## Task 6: E2E测试

**Files:**
- Create: `src/frontend/tests/e2e/05-dynamic-menus.spec.ts`

- [ ] **Step 1: 创建动态菜单E2E测试**

```typescript
test.describe('动态菜单加载', () => {
  test('admin用户应该看到系统管理菜单', async ({ page }) => {
    await login(page, 'admin', 'admin123')
    await expect(page.locator('text=系统管理')).toBeVisible()
  })

  test('user用户不应该看到系统管理菜单', async ({ page }) => {
    await login(page, 'testuser', 'Test123456!')
    await expect(page.locator('text=系统管理')).not.toBeVisible()
  })

  test('无权限访问应该被重定向到403', async ({ page }) => {
    await login(page, 'testuser', 'Test123456!')
    await page.goto('http://localhost:5173/system/users')
    await expect(page).toHaveURL('/403')
  })
})
```

---

## 验收标准

- [ ] 不同角色登录看到不同菜单
- [ ] 无权限访问被拦截（403）
- [ ] 菜单正确展开/收起
- [ ] 图标正确显示

---

**下一步**: 完成 Phase 4: 审计日志实施计划
