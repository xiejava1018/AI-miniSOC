-- 初始化菜单数据

-- 业务菜单
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('概览仪表板', '/dashboard', 'DataAnalysis', 1, true),
('资产管理', '/assets', 'Monitor', 2, true),
('事件管理', '/incidents', 'Warning', 3, true),
('告警管理', '/alerts', 'Bell', 4, true)
ON CONFLICT (path) DO NOTHING;

-- 系统管理（父菜单 - 使用空字符串path）
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('系统管理', '', 'Setting', 5, true)
ON CONFLICT (name, path) DO NOTHING;

-- 系统管理子菜单
INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '用户管理',
    '/system/users',
    'User',
    1,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/users');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '角色管理',
    '/system/roles',
    'Lock',
    2,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/roles');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '菜单管理',
    '/system/menus',
    'Menu',
    3,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/menus');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '审计日志',
    '/system/audit',
    'Document',
    4,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/audit');

-- 显示插入结果
SELECT id, parent_id, name, path, icon, sort_order FROM soc_menus ORDER BY sort_order;
