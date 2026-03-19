-- src/backend/migrations/postgresql/001_system_management.sql
-- 系统管理模块数据库表
-- 版本: 1.0
-- 日期: 2026-03-19

-- 启用UUID扩展（如果需要）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- 1. 角色表 (soc_roles)
-- ============================================
CREATE TABLE soc_roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    is_system BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_role_code CHECK (code IN ('admin', 'user', 'readonly'))
);

CREATE INDEX idx_roles_code ON soc_roles(code);

-- ============================================
-- 2. 菜单表 (soc_menus)
-- ============================================
CREATE TABLE soc_menus (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT REFERENCES soc_menus(id),
    name VARCHAR(50) NOT NULL,
    path VARCHAR(200) NOT NULL,
    icon VARCHAR(50),
    sort_order INTEGER DEFAULT 0,
    is_visible BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_menus_parent ON soc_menus(parent_id);
CREATE INDEX idx_menus_path ON soc_menus(path);

-- ============================================
-- 3. 用户表 (soc_users)
-- ============================================
CREATE TABLE soc_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE,
    full_name VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    role_id BIGINT NOT NULL REFERENCES soc_roles(id),
    last_login_at TIMESTAMP,
    password_changed_at TIMESTAMP,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_status CHECK (status IN ('active', 'locked', 'disabled'))
);

CREATE INDEX idx_users_username ON soc_users(username);
CREATE INDEX idx_users_role ON soc_users(role_id);
CREATE INDEX idx_users_email ON soc_users(email);
CREATE INDEX idx_users_status ON soc_users(status);

-- ============================================
-- 4. 角色菜单关联表 (soc_role_menus)
-- ============================================
CREATE TABLE soc_role_menus (
    role_id BIGINT NOT NULL REFERENCES soc_roles(id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES soc_menus(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, menu_id)
);

CREATE INDEX idx_role_menus_role ON soc_role_menus(role_id);
CREATE INDEX idx_role_menus_menu ON soc_role_menus(menu_id);

-- ============================================
-- 5. 系统配置表 (soc_system_config)
-- ============================================
CREATE TABLE soc_system_config (
    id BIGSERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    value_type VARCHAR(20) DEFAULT 'string',
    is_encrypted BOOLEAN DEFAULT false,
    description TEXT,
    updated_by BIGINT REFERENCES soc_users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

CREATE INDEX idx_config_category ON soc_system_config(category);

-- ============================================
-- 6. 用户会话表 (soc_user_sessions)
-- ============================================
CREATE TABLE soc_user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    refresh_token_hash VARCHAR(64),
    ip_address VARCHAR(45),
    user_agent TEXT,
    login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logout_at TIMESTAMP,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_sessions_user ON soc_user_sessions(user_id);
CREATE INDEX idx_sessions_token ON soc_user_sessions(token_hash);
CREATE INDEX idx_sessions_active ON soc_user_sessions(is_active, last_activity_at);

-- ============================================
-- 7. 密码历史表 (soc_password_history)
-- ============================================
CREATE TABLE soc_password_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_password_history_user ON soc_password_history(user_id, created_at DESC);

-- ============================================
-- 8. 密码重置令牌表 (soc_password_reset_tokens)
-- ============================================
CREATE TABLE soc_password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id),
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reset_tokens_user ON soc_password_reset_tokens(user_id);
CREATE INDEX idx_reset_tokens_hash ON soc_password_reset_tokens(token_hash);
CREATE INDEX idx_reset_tokens_expires ON soc_password_reset_tokens(expires_at);

-- ============================================
-- 9. API限流表 (soc_rate_limits)
-- ============================================
CREATE TABLE soc_rate_limits (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES soc_users(id),
    ip_address VARCHAR(45) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    blocked_until TIMESTAMP
);

CREATE INDEX idx_rate_limits_user ON soc_rate_limits(user_id, window_start);
CREATE INDEX idx_rate_limits_ip ON soc_rate_limits(ip_address, window_start);

-- ============================================
-- 10. 审计日志表 (soc_audit_logs)
-- ============================================
CREATE TABLE soc_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES soc_users(id),
    username VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id BIGINT,
    resource_name VARCHAR(200),
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    session_id BIGINT REFERENCES soc_user_sessions(id),
    request_id VARCHAR(36),
    status VARCHAR(20) DEFAULT 'success',
    error_message TEXT,
    log_hash VARCHAR(64),
    prev_log_hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON soc_audit_logs(user_id);
CREATE INDEX idx_audit_action ON soc_audit_logs(action);
CREATE INDEX idx_audit_resource ON soc_audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_created ON soc_audit_logs(created_at);
CREATE INDEX idx_audit_request ON soc_audit_logs(request_id);
CREATE INDEX idx_audit_hash_chain ON soc_audit_logs(prev_log_hash, log_hash);

-- ============================================
-- 11. 审计日志哈希链触发器
-- ============================================
CREATE OR REPLACE FUNCTION calculate_audit_log_hash()
RETURNS TRIGGER AS $$
DECLARE
  log_data TEXT;
  prev_hash VARCHAR(64);
BEGIN
  SELECT log_hash INTO prev_hash
  FROM soc_audit_logs
  WHERE id < NEW.id
  ORDER BY id DESC
  LIMIT 1;

  log_data := NEW.user_id::TEXT || NEW.username || NEW.action ||
              COALESCE(NEW.resource_type, '') || COALESCE(NEW.resource_id::TEXT, '') ||
              COALESCE(NEW.old_values::TEXT, '') || COALESCE(NEW.new_values::TEXT, '') ||
              NEW.created_at::TEXT || COALESCE(prev_hash, '');

  NEW.log_hash := encode(digest(log_data, 'sha256'), 'hex');
  NEW.prev_log_hash := prev_hash;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_hash_trigger
  BEFORE INSERT ON soc_audit_logs
  FOR EACH ROW
  EXECUTE FUNCTION calculate_audit_log_hash();

-- ============================================
-- 12. 初始化默认数据
-- ============================================

-- 插入默认角色
INSERT INTO soc_roles (id, name, code, description, is_system) VALUES
  (1, '管理员', 'admin', '系统管理员，拥有所有权限', true),
  (2, '普通用户', 'user', '普通用户，可使用业务功能', true),
  (3, '只读用户', 'readonly', '只读用户，仅可查看数据', true);

-- 插入默认菜单
INSERT INTO soc_menus (id, parent_id, name, path, icon, sort_order) VALUES
  -- 业务菜单
  (1, NULL, '概览仪表板', '/dashboard', 'DataAnalysis', 1),
  (2, NULL, '资产管理', '/assets', 'Monitor', 2),
  (3, NULL, '事件管理', '/incidents', 'Warning', 3),
  (4, NULL, '告警中心', '/alerts', 'Bell', 4),
  -- 系统管理（父菜单）
  (10, NULL, '系统管理', NULL, 'Setting', 5);

-- 系统管理子菜单
INSERT INTO soc_menus (id, parent_id, name, path, icon, sort_order) VALUES
  (11, 10, '用户管理', '/system/users', 'User', 1),
  (12, 10, '角色管理', '/system/roles', 'Lock', 2),
  (13, 10, '菜单管理', '/system/menus', 'Menu', 3),
  (14, 10, '系统配置', '/system/config', 'Setting', 4),
  (15, 10, '审计日志', '/system/audit', 'Document', 5);

-- 分配菜单权限
-- 管理员拥有所有菜单
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 1, id FROM soc_menus;

-- 普通用户拥有业务菜单（不含系统管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 2, id FROM soc_menus WHERE id NOT BETWEEN 10 AND 15;

-- 只读用户拥有业务菜单（不含系统管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT 3, id FROM soc_menus WHERE id NOT BETWEEN 10 AND 15;

-- 插入默认配置
INSERT INTO soc_system_config (category, key, value, value_type, description) VALUES
  -- 基础配置
  ('basic', 'system_name', 'AI-miniSOC', 'string', '系统名称'),
  ('basic', 'theme', 'dark', 'string', '默认主题'),
  ('basic', 'timezone', 'Asia/Shanghai', 'string', '时区'),
  ('basic', 'language', 'zh-CN', 'string', '语言'),

  -- 安全策略
  ('security', 'password_min_length', '8', 'number', '密码最小长度'),
  ('security', 'password_require_special', 'true', 'boolean', '需要特殊字符'),
  ('security', 'password_expire_days', '90', 'number', '密码过期天数'),
  ('security', 'login_max_attempts', '5', 'number', '最大登录尝试次数'),
  ('security', 'login_lockout_minutes', '30', 'number', '锁定时长（分钟）'),
  ('security', 'session_timeout_minutes', '120', 'number', '会话超时（分钟）');

-- ============================================
-- 13. 创建默认管理员账户的SQL脚本（需要在应用层生成密码哈希）
-- ============================================
-- 注意：默认管理员账户需要在应用层创建，因为密码需要bcrypt加密
-- 使用 init_db.py 脚本创建管理员账户
