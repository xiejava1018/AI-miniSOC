-- 初始化菜单数据

-- 业务菜单
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('概览仪表板', '/dashboard', 'DataAnalysis', 1, true),
('资产管理', '/assets', 'Monitor', 2, true),
('事件管理', '/incidents', 'Warning', 3, true),
('告警管理', '/alerts', 'Bell', 4, true)
ON CONFLICT (path) DO NOTHING;

-- 系统管理（父菜单 - 顶级菜单 path 与路由别名一致）
-- 注：早期 init 用过 '' 作为 path，但 menu 迁移（a0b1c2d3e4f5 / e2f3g4h5i6j7 等）
-- 一律按 WHERE path='/system' 定位父菜单，'' 会导致种入静默 0 行。
-- 现统一为 '/system'；历史 '' 行由 e2f3g4h5i6j7 兜底改写。
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('系统管理', '/system', 'Setting', 5, true)
ON CONFLICT (name, path) DO NOTHING;

-- 系统管理子菜单
INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '用户管理',
    '/system/user',
    'User',
    1,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/user');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '角色管理',
    '/system/role',
    'Lock',
    2,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/role');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '菜单管理',
    '/system/menu',
    'Menu',
    3,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/menu');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '审计日志',
    '/system/audit-log',
    'Document',
    4,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/audit-log');

-- 显示插入结果
SELECT id, parent_id, name, path, icon, sort_order FROM soc_menus ORDER BY sort_order;
