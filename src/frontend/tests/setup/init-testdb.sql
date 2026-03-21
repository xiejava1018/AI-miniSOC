-- AI-miniSOC E2E测试数据库初始化脚本
-- 在192.168.0.42的AI-miniSOC-testdb上执行

-- 1. 创建枚举类型
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_status') THEN
        CREATE TYPE user_status AS ENUM ('active', 'locked', 'disabled');
    END IF;
END $$;

-- 2. 创建角色表
DROP TABLE IF EXISTS soc_roles CASCADE;
CREATE TABLE soc_roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    is_system BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 创建用户表
DROP TABLE IF EXISTS soc_users CASCADE;
CREATE TABLE soc_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE,
    full_name VARCHAR(100),
    role_id INTEGER REFERENCES soc_roles(id),
    status user_status DEFAULT 'active',
    is_superuser BOOLEAN DEFAULT false,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 创建菜单表
DROP TABLE IF EXISTS soc_menus CASCADE;
CREATE TABLE soc_menus (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    title VARCHAR(100) NOT NULL,
    path VARCHAR(200),
    icon VARCHAR(50),
    parent_id INTEGER REFERENCES soc_menus(id),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. 创建角色菜单关联表
DROP TABLE IF EXISTS soc_role_menus CASCADE;
CREATE TABLE soc_role_menus (
    id SERIAL PRIMARY KEY,
    role_id INTEGER REFERENCES soc_roles(id) ON DELETE CASCADE,
    menu_id INTEGER REFERENCES soc_menus(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role_id, menu_id)
);

-- 6. 创建索引
CREATE INDEX idx_soc_users_username ON soc_users(username);
CREATE INDEX idx_soc_users_email ON soc_users(email);
CREATE INDEX idx_soc_users_status ON soc_users(status);
CREATE INDEX idx_soc_users_role_id ON soc_users(role_id);

-- 7. 插入测试菜单
INSERT INTO soc_menus (name, title, path, icon, sort_order) VALUES
('dashboard', '仪表板', '/dashboard', 'Odometer', 1),
('assets', '资产管理', '/assets', 'Monitor', 2),
('incidents', '事件管理', '/incidents', 'Warning', 3),
('alerts', '告警管理', '/alerts', 'Bell', 4),
('system', '系统管理', '/system', 'Setting', 5),
('users', '用户管理', '/system/users', 'User', 6);

-- 8. 插入测试角色
INSERT INTO soc_roles (name, code, description, is_system) VALUES
('管理员', 'admin', '系统管理员，拥有所有权限', true),
('普通用户', 'user', '普通用户角色', false),
('只读用户', 'readonly', '只读用户角色', false);

-- 9. 插入管理员用户 (密码: admin123)
-- 密码使用bcrypt hash (cost=12)
INSERT INTO soc_users (id, username, password_hash, email, full_name, role_id, status, is_superuser)
VALUES (1, 'admin', '$2b$12$9bUors.SDcFEiQAK2yVlD.xg/CtlWFY0cyJvx1bbtvM8VTnqbHHzG', 'admin@example.com', '系统管理员', 1, 'active', true);

-- 10. 插入测试用户 (密码: Test123456!)
INSERT INTO soc_users (username, password_hash, email, full_name, role_id, status) VALUES
('testuser', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'test@example.com', '测试用户', 2, 'active'),
('testuser2', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'test2@example.com', '测试用户2', 2, 'active'),
('deletable_user', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'deletable@example.com', '可删除用户', 2, 'active'),
('locked_user', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'locked@example.com', '锁定用户', 2, 'locked'),
('disabled_user', '$2b$12$7e9eBjYYJacdsFWa6kuQpOX5i14v.TuTV3qz628IndRF5rHEzaRf.', 'disabled@example.com', '禁用用户', 2, 'disabled');

-- 11. 分配角色菜单权限
-- 管理员可以访问所有菜单
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 1, id FROM soc_menus;

-- 普通用户可以访问仪表板、资产、事件、告警
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 2, id FROM soc_menus WHERE name IN ('dashboard', 'assets', 'incidents', 'alerts');

-- 只读用户只能访问仪表板
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 3, id FROM soc_menus WHERE name = 'dashboard';

-- 12. 显示创建结果
SELECT '✅ Database initialized successfully!' AS status;
SELECT 'Tables created:' AS info;
SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'soc_%' ORDER BY tablename;
SELECT 'Users created:' AS info;
SELECT username, full_name, status FROM soc_users;
