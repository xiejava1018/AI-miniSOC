-- tests/setup/test-seed.sql
-- 测试数据种子文件
-- 密码使用bcrypt生成的hash值 (cost=12)

-- ============================================================================
-- 测试角色数据
-- ============================================================================
INSERT INTO soc_roles (id, name, code, description, is_system) VALUES
(1, '系统管理员', 'admin', '系统管理员，拥有所有权限', true),
(2, '普通用户', 'user', '普通用户角色', false),
(3, '只读用户', 'readonly', '只读用户角色', false)
ON CONFLICT (code) DO NOTHING;

-- ============================================================================
-- 测试用户数据
-- 密码说明:
--   admin123     -> $2b$12$9bUors.SDcFEiQAK2yVlD.xg/CtlWFY0cyJvx1bbtvM8VTnqbHHzG
--   Test123456!  -> $2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.
-- ============================================================================

-- 管理员用户 (密码: admin123)
INSERT INTO soc_users (id, username, hashed_password, email, full_name, role_id, status, is_superuser)
VALUES (1, 'admin', '$2b$12$9bUors.SDcFEiQAK2yVlD.xg/CtlWFY0cyJvx1bbtvM8VTnqbHHzG', 'admin@example.com', '系统管理员', 1, 'active', true)
ON CONFLICT (username) DO NOTHING;

-- 普通测试用户 (密码: Test123456!)
INSERT INTO soc_users (username, hashed_password, email, full_name, role_id, status)
VALUES
('testuser', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'test@example.com', '测试用户', 2, 'active'),
('testuser2', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'test2@example.com', '测试用户2', 2, 'active')
ON CONFLICT (username) DO NOTHING;

-- 可删除的测试用户 (用于删除测试)
INSERT INTO soc_users (username, hashed_password, email, full_name, role_id, status)
VALUES ('deletable_user', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'deletable@example.com', '可删除用户', 2, 'active')
ON CONFLICT (username) DO NOTHING;

-- 被锁定的测试用户 (用于登录失败测试)
INSERT INTO soc_users (username, hashed_password, email, full_name, role_id, status, failed_login_attempts, locked_until)
VALUES ('locked_user', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'locked@example.com', '被锁定用户', 2, 'locked', 5, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
ON CONFLICT (username) DO NOTHING;

-- 被禁用的测试用户
INSERT INTO soc_users (username, hashed_password, email, full_name, role_id, status)
VALUES ('disabled_user', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'disabled@example.com', '被禁用用户', 2, 'disabled')
ON CONFLICT (username) DO NOTHING;

-- ============================================================================
-- 测试菜单权限数据
-- ============================================================================

-- 为普通用户分配基础菜单权限（仪表板、资产管理、事件管理、告警管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 2, id FROM soc_menus WHERE name IN ('仪表板', '资产管理', '事件管理', '告警管理')
ON CONFLICT DO NOTHING;

-- 为只读用户分配查看权限（仅仪表板）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 3, id FROM soc_menus WHERE name = '仪表板'
ON CONFLICT DO NOTHING;
