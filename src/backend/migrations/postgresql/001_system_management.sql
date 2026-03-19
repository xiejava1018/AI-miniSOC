-- ============================================================================
-- AI-miniSOC System Management Module Database Migration
-- Version: 001
-- Description: Create tables for RBAC, user management, and audit logging
-- ============================================================================

-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- Table: soc_roles
-- Description: Role definitions for RBAC
-- ============================================================================
CREATE TABLE soc_roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    code VARCHAR(20) NOT NULL UNIQUE,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_role_code CHECK (code IN ('admin', 'user', 'readonly'))
;

COMMENT ON TABLE soc_roles IS 'Role definitions for role-based access control';
COMMENT ON COLUMN soc_roles.is_system IS 'System roles cannot be deleted';

-- Indexes for soc_roles
CREATE INDEX idx_soc_roles_code ON soc_roles(code);

-- ============================================================================
-- Table: soc_menus
-- Description: Menu/navigation structure with parent-child relationships
-- ============================================================================
CREATE TABLE soc_menus (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT REFERENCES soc_menus(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    path VARCHAR(200) NOT NULL,
    icon VARCHAR(50),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_visible BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_menus IS 'Menu and navigation structure with hierarchical support';
COMMENT ON COLUMN soc_menus.parent_id IS 'Parent menu ID for hierarchical structure';

-- Indexes for soc_menus
CREATE INDEX idx_soc_menus_parent_id ON soc_menus(parent_id);
CREATE INDEX idx_soc_menus_sort_order ON soc_menus(sort_order);
CREATE INDEX idx_soc_menus_is_visible ON soc_menus(is_visible);

-- ============================================================================
-- Table: soc_users
-- Description: User accounts with authentication and profile information
-- ============================================================================
CREATE TABLE soc_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    role_id BIGINT NOT NULL REFERENCES soc_roles(id) ON DELETE RESTRICT,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_user_status CHECK (status IN ('active', 'locked', 'disabled'))
;

COMMENT ON TABLE soc_users IS 'User accounts with authentication and profile information';
COMMENT ON COLUMN soc_users.hashed_password IS 'Bcrypt hash of user password';
COMMENT ON COLUMN soc_users.failed_login_attempts IS 'Counter for account lockout after failed attempts';

-- Indexes for soc_users
CREATE INDEX idx_soc_users_username ON soc_users(username);
CREATE INDEX idx_soc_users_email ON soc_users(email);
CREATE INDEX idx_soc_users_role_id ON soc_users(role_id);
CREATE INDEX idx_soc_users_status ON soc_users(status);

-- ============================================================================
-- Table: soc_role_menus
-- Description: Many-to-many relationship between roles and menus
-- ============================================================================
CREATE TABLE soc_role_menus (
    role_id BIGINT NOT NULL REFERENCES soc_roles(id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES soc_menus(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, menu_id)
);

COMMENT ON TABLE soc_role_menus IS 'Role-menu permissions for RBAC';

-- Indexes for soc_role_menus
CREATE INDEX idx_soc_role_menus_role_id ON soc_role_menus(role_id);
CREATE INDEX idx_soc_role_menus_menu_id ON soc_role_menus(menu_id);

-- ============================================================================
-- Table: soc_system_config
-- Description: System configuration key-value store
-- ============================================================================
CREATE TABLE soc_system_config (
    id BIGSERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    value_type VARCHAR(20) NOT NULL DEFAULT 'string' CHECK (value_type IN ('string', 'integer', 'boolean', 'json'),
    description TEXT,
    is_encrypted BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by BIGINT REFERENCES soc_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

COMMENT ON TABLE soc_system_config IS 'System configuration key-value store';
COMMENT ON COLUMN soc_system_config.is_encrypted IS 'Whether the value is encrypted (PGP)';

-- Indexes for soc_system_config
CREATE INDEX idx_soc_system_config_category ON soc_system_config(category);
CREATE INDEX idx_soc_system_config_key ON soc_system_config(key);

-- ============================================================================
-- Table: soc_user_sessions
-- Description: User session tracking for JWT tokens
-- ============================================================================
CREATE TABLE soc_user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    refresh_token_hash VARCHAR(64),
    ip_address VARCHAR(45),
    user_agent TEXT,
    login_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    logout_at TIMESTAMP WITH TIME ZONE,
    last_activity_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE soc_user_sessions IS 'User session tracking for JWT token management';
COMMENT ON COLUMN soc_user_sessions.token_hash IS 'SHA-256 hash of JWT token for security';

-- Indexes for soc_user_sessions
CREATE INDEX idx_soc_user_sessions_user_id ON soc_user_sessions(user_id);
CREATE INDEX idx_soc_user_sessions_token_hash ON soc_user_sessions(token_hash);
CREATE INDEX idx_soc_user_sessions_is_active ON soc_user_sessions(is_active);
CREATE INDEX idx_soc_user_sessions_last_activity ON soc_user_sessions(is_active, last_activity_at);

-- ============================================================================
-- Table: soc_password_history
-- Description: Password history to prevent reuse
-- ============================================================================
CREATE TABLE soc_password_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_password_history IS 'Password history for preventing password reuse';

-- Indexes for soc_password_history
CREATE INDEX idx_soc_password_history_user_id ON soc_password_history(user_id, created_at DESC);

-- ============================================================================
-- Table: soc_password_reset_tokens
-- Description: Password reset token storage
-- ============================================================================
CREATE TABLE soc_password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_password_reset_tokens IS 'Password reset tokens for self-service password reset';

-- Indexes for soc_password_reset_tokens
CREATE INDEX idx_soc_password_reset_tokens_user_id ON soc_password_reset_tokens(user_id);
CREATE INDEX idx_soc_password_reset_tokens_token_hash ON soc_password_reset_tokens(token_hash);
CREATE INDEX idx_soc_password_reset_tokens_expires_at ON soc_password_reset_tokens(expires_at);

-- ============================================================================
-- Table: soc_rate_limits
-- Description: API rate limiting
-- ============================================================================
CREATE TABLE soc_rate_limits (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES soc_users(id),
    ip_address VARCHAR(45) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    blocked_until TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE soc_rate_limits IS 'API rate limiting for DDoS protection';

-- Indexes for soc_rate_limits
CREATE INDEX idx_soc_rate_limits_user_id ON soc_rate_limits(user_id, window_start);
CREATE INDEX idx_soc_rate_limits_ip_address ON soc_rate_limits(ip_address, window_start);

-- ============================================================================
-- Table: soc_audit_logs
-- Description: Comprehensive audit logging with tamper-proof hash chain
-- ============================================================================
CREATE TABLE soc_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES soc_users(id) ON DELETE SET NULL,
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
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    error_message TEXT,
    prev_log_hash VARCHAR(64),
    log_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_audit_logs IS 'Comprehensive audit log with tamper-proof hash chain';
COMMENT ON COLUMN soc_audit_logs.prev_log_hash IS 'Hash of previous log entry for chain verification';
COMMENT ON COLUMN soc_audit_logs.log_hash IS 'SHA-256 hash of this entry plus previous hash';

-- Indexes for soc_audit_logs
CREATE INDEX idx_soc_audit_logs_user_id ON soc_audit_logs(user_id);
CREATE INDEX idx_soc_audit_logs_username ON soc_audit_logs(username);
CREATE INDEX idx_soc_audit_logs_action ON soc_audit_logs(action);
CREATE INDEX idx_soc_audit_logs_resource_type ON soc_audit_logs(resource_type);
CREATE INDEX idx_soc_audit_logs_resource_id ON soc_audit_logs(resource_id);
CREATE INDEX idx_soc_audit_logs_created_at ON soc_audit_logs(created_at);
CREATE INDEX idx_soc_audit_logs_request_id ON soc_audit_logs(request_id);
CREATE INDEX idx_soc_audit_logs_hash_chain ON soc_audit_logs(prev_log_hash, log_hash);

-- ============================================================================
-- Trigger Function: calculate_audit_log_hash
-- Description: Creates a hash chain for tamper-proof audit logs
-- ============================================================================
CREATE OR REPLACE FUNCTION calculate_audit_log_hash()
RETURNS TRIGGER AS $$
DECLARE
    log_data TEXT;
    prev_hash VARCHAR(64);
BEGIN
    -- Get the hash of the previous log entry
    SELECT log_hash INTO prev_hash
    FROM soc_audit_logs
    WHERE id < NEW.id
    ORDER BY id DESC
    LIMIT 1;

    -- Calculate the current log hash
    log_data := COALESCE(NEW.user_id::TEXT, '') ||
                NEW.username ||
                NEW.action ||
                COALESCE(NEW.resource_type, '') ||
                COALESCE(NEW.resource_id::TEXT, '') ||
                COALESCE(NEW.resource_name, '') ||
                COALESCE(NEW.old_values::TEXT, '') ||
                COALESCE(NEW.new_values::TEXT, '') ||
                NEW.created_at::TEXT ||
                COALESCE(prev_hash, '');

    NEW.log_hash := encode(digest(log_data, 'sha256'), 'hex');
    NEW.prev_log_hash := prev_hash;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_audit_log_hash() IS 'Calculates SHA-256 hash for audit log chain integrity';

-- Create trigger for audit logs with correct name
CREATE TRIGGER audit_log_hash_trigger
    BEFORE INSERT ON soc_audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION calculate_audit_log_hash();

-- ============================================================================
-- Insert Default Data
-- ============================================================================

-- Insert default roles
INSERT INTO soc_roles (name, code, description, is_system) VALUES
('系统管理员', 'admin', '拥有系统所有权限的超级管理员', TRUE),
('普通用户', 'user', '具有业务操作权限的普通用户', TRUE),
('只读用户', 'readonly', '仅具有查看权限的用户', TRUE);

-- Insert default menu structure
-- Level 1 menus
INSERT INTO soc_menus (parent_id, name, path, icon, sort_order) VALUES
(NULL, '仪表板', '/dashboard', 'Dashboard', 1),
(NULL, '资产管理', '/assets', 'Assets', 2),
(NULL, '事件管理', '/incidents', 'AlertTriangle', 3),
(NULL, '告警管理', '/alerts', 'Bell', 4),
(NULL, '系统管理', '/system', 'Settings', 5);

-- Get the ID of system management directory
INSERT INTO soc_menus (parent_id, name, path, icon, sort_order)
SELECT id, '用户管理', '/system/users', 'Users', 1
FROM soc_menus WHERE name = '系统管理';

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order)
SELECT id, '角色管理', '/system/roles', 'Shield', 2
FROM soc_menus WHERE name = '系统管理';

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order)
SELECT id, '菜单管理', '/system/menus', 'Menu', 3
FROM soc_menus WHERE name = '系统管理';

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order)
SELECT id, '审计日志', '/system/audit', 'FileText', 4
FROM soc_menus WHERE name = '系统管理';

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order)
SELECT id, '系统配置', '/system/config', 'Settings', 5
FROM soc_menus WHERE name = '系统管理';

-- Assign all menus to admin role
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM soc_roles r
CROSS JOIN soc_menus m
WHERE r.code = 'admin';

-- Assign business menus to user role (exclude system management)
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM soc_roles r
CROSS JOIN soc_menus m
WHERE r.code = 'user'
  AND m.name NOT IN ('系统管理');

-- Assign business menus to readonly role (exclude system management)
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM soc_roles r
CROSS JOIN soc_menus m
WHERE r.code = 'readonly'
  AND m.name NOT IN ('系统管理');

-- Insert default system configurations
INSERT INTO soc_system_config (category, key, value, value_type, description) VALUES
-- Basic config
('basic', 'system_name', 'AI-miniSOC', 'string', '系统名称'),
('basic', 'theme', 'dark', 'string', '默认主题'),
('basic', 'timezone', 'Asia/Shanghai', 'string', '时区'),
-- Security config
('security', 'password_min_length', '8', 'integer', '密码最小长度'),
('security', 'password_max_length', '128', 'integer', '密码最大长度'),
('security', 'password_require_uppercase', 'true', 'boolean', '密码是否需要大写字母'),
('security', 'password_require_lowercase', 'true', 'boolean', '密码是否需要小写字母'),
('security', 'password_require_number', 'true', 'boolean', '密码是否需要数字'),
('security', 'password_require_special', 'true', 'boolean', '密码是否需要特殊字符'),
('security', 'password_history_count', '5', 'integer', '记录历史密码数量（防止重复使用）'),
('security', 'password_expire_days', '90', 'integer', '密码过期天数（0表示永不过期）'),
('security', 'login_max_attempts', '5', 'integer', '最大失败登录次数'),
('security', 'account_lockout_minutes', '30', 'integer', '账户锁定时长（分钟）'),
('security', 'session_timeout_minutes', '60', 'integer', '会话超时时间（分钟）'),
('security', 'jwt_secret', 'CHANGE_ME_IN_PRODUCTION', 'string', 'JWT签名密钥（生产环境必须修改）'),
('security', 'jwt_access_token_expire_minutes', '30', 'integer', 'JWT访问令牌过期时间（分钟）'),
('security', 'jwt_refresh_refresh_token_expire_days', '7', 'integer', 'JWT刷新令牌过期时间（天）'),
('rate_limit', 'enabled', 'true', 'boolean', '是否启用速率限制'),
('rate_limit', 'requests_per_minute', '60', 'integer', '每分钟请求限制'),
('rate_limit', 'requests_per_hour', '1000', 'integer', '每小时请求限制'),
('audit_log', 'retention_days', '90', 'integer', '审计日志保留天数'),
('audit_log', 'hash_chain_enabled', 'true', 'boolean', '是否启用审计日志哈希链');

-- ============================================================================
-- Migration complete
-- ============================================================================
