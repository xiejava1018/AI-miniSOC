-- 初始化系统管理菜单（修正版）
-- 为系统管理父菜单添加title
UPDATE soc_menus SET title = name WHERE name = 'system' AND title IS NULL;

-- 为用户管理添加title
UPDATE soc_menus SET title = name WHERE name = 'users' AND title IS NULL;

-- 插入角色管理菜单
INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='system'),
    'roles',
    '角色管理',
    '/system/roles',
    'Lock',
    2,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/roles');

-- 插入菜单管理
INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='system'),
    'menus',
    '菜单管理',
    '/system/menus',
    'Menu',
    3,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/menus');

-- 插入审计日志
INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='system'),
    'audit-logs',
    '审计日志',
    '/system/audit-logs',
    'Document',
    4,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/audit-logs');

-- 修复用户管理的sort_order
UPDATE soc_menus SET sort_order = 1 WHERE path = '/system/users';

-- 显示插入结果
SELECT id, parent_id, name, title, path, icon, sort_order FROM soc_menus ORDER BY parent_id NULLS LAST, sort_order;
