-- 初始化系统内置角色

-- 系统内置角色
INSERT INTO soc_roles (name, code, description, is_system) VALUES
('管理员', 'admin', '系统管理员，拥有所有权限', true),
('普通用户', 'user', '普通用户，可使用业务功能', true),
('只读用户', 'readonly', '只读用户，仅可查看数据', true)
ON CONFLICT (code) DO NOTHING;

-- 显示插入结果
SELECT id, name, code, is_system FROM soc_roles WHERE code IN ('admin', 'user', 'readonly');
