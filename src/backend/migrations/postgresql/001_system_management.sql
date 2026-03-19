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
    role_name VARCHAR(50) NOT NULL UNIQUE,
    role_code VARCHAR(20) NOT NULL UNIQUE,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_roles IS 'Role definitions for role-based access control';
COMMENT ON COLUMN soc_roles.is_system IS 'System roles cannot be deleted';

-- Indexes for soc_roles
CREATE INDEX idx_soc_roles_role_code ON soc_roles(role_code);
CREATE INDEX idx_soc_roles_is_active ON soc_roles(is_active);

-- ============================================================================
-- Table: soc_menus
-- Description: Menu/navigation structure with parent-child relationships
-- ============================================================================
CREATE TABLE soc_menus (
    id BIGSERIAL PRIMARY KEY,
    menu_name VARCHAR(100) NOT NULL,
    menu_code VARCHAR(50) NOT NULL UNIQUE,
    parent_id BIGINT REFERENCES soc_menus(id) ON DELETE CASCADE,
    menu_type VARCHAR(20) NOT NULL CHECK (menu_type IN ('directory', 'menu', 'button')),
    icon VARCHAR(50),
    path VARCHAR(200),
    component VARCHAR(200),
    permission VARCHAR(100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_visible BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_menus IS 'Menu and navigation structure with hierarchical support';
COMMENT ON COLUMN soc_menus.parent_id IS 'Parent menu ID for hierarchical structure';
COMMENT ON COLUMN soc_menus.menu_type IS 'Type: directory (group), menu (page), button (action)';

-- Indexes for soc_menus
CREATE INDEX idx_soc_menus_parent_id ON soc_menus(parent_id);
CREATE INDEX idx_soc_menus_menu_code ON soc_menus(menu_code);
CREATE INDEX idx_soc_menus_sort_order ON soc_menus(sort_order);
CREATE INDEX idx_soc_menus_is_active ON soc_menus(is_active);

-- ============================================================================
-- Table: soc_users
-- Description: User accounts with authentication and profile information
-- ============================================================================
CREATE TABLE soc_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    phone VARCHAR(20),
    avatar_url VARCHAR(500),
    role_id BIGINT NOT NULL REFERENCES soc_roles(id) ON DELETE RESTRICT,
    department VARCHAR(100),
    position VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    locked_until TIMESTAMP WITH TIME ZONE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_login_ip INET,
    password_changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_users IS 'User accounts with authentication and profile information';
COMMENT ON COLUMN soc_users.hashed_password IS 'Bcrypt hash of user password';
COMMENT ON COLUMN soc_users.failed_login_attempts IS 'Counter for account lockout after failed attempts';
COMMENT ON COLUMN soc_users.must_change_password IS 'Force password change on next login';

-- Indexes for soc_users
CREATE INDEX idx_soc_users_username ON soc_users(username);
CREATE INDEX idx_soc_users_email ON soc_users(email);
CREATE INDEX idx_soc_users_role_id ON soc_users(role_id);
CREATE INDEX idx_soc_users_is_active ON soc_users(is_active);
CREATE INDEX idx_soc_users_is_locked ON soc_users(is_locked);

-- ============================================================================
-- Table: soc_role_menus
-- Description: Many-to-many relationship between roles and menus
-- ============================================================================
CREATE TABLE soc_role_menus (
    id BIGSERIAL PRIMARY KEY,
    role_id BIGINT NOT NULL REFERENCES soc_roles(id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES soc_menus(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role_id, menu_id)
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
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    config_type VARCHAR(20) NOT NULL DEFAULT 'string' CHECK (config_type IN ('string', 'integer', 'boolean', 'json')),
    description TEXT,
    is_encrypted BOOLEAN NOT NULL DEFAULT FALSE,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_system_config IS 'System configuration key-value store';
COMMENT ON COLUMN soc_system_config.is_encrypted IS 'Whether the value is encrypted (PGP)';
COMMENT ON COLUMN soc_system_config.is_public IS 'Whether non-admin users can read this config';

-- Indexes for soc_system_config
CREATE INDEX idx_soc_system_config_config_key ON soc_system_config(config_key);

-- ============================================================================
-- Table: soc_user_sessions
-- Description: User session tracking for JWT tokens
-- ============================================================================
CREATE TABLE soc_user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    refresh_token_hash VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    device_type VARCHAR(50),
    browser VARCHAR(50),
    os VARCHAR(50),
    location VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_activity_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_user_sessions IS 'User session tracking for JWT token management';
COMMENT ON COLUMN soc_user_sessions.token_hash IS 'SHA-256 hash of JWT token for security';

-- Indexes for soc_user_sessions
CREATE INDEX idx_soc_user_sessions_user_id ON soc_user_sessions(user_id);
CREATE INDEX idx_soc_user_sessions_token_hash ON soc_user_sessions(token_hash);
CREATE INDEX idx_soc_user_sessions_is_active ON soc_user_sessions(is_active);
CREATE INDEX idx_soc_user_sessions_expires_at ON soc_user_sessions(expires_at);

-- ============================================================================
-- Table: soc_password_history
-- Description: Password history to prevent reuse
-- ============================================================================
CREATE TABLE soc_password_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    hashed_password VARCHAR(255) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by BIGINT REFERENCES soc_users(id) ON DELETE SET NULL
);

COMMENT ON TABLE soc_password_history IS 'Password history for preventing password reuse';

-- Indexes for soc_password_history
CREATE INDEX idx_soc_password_history_user_id ON soc_password_history(user_id);
CREATE INDEX idx_soc_password_history_changed_at ON soc_password_history(changed_at);

-- ============================================================================
-- Table: soc_password_reset_tokens
-- Description: Password reset token storage
-- ============================================================================
CREATE TABLE soc_password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    ip_address INET,
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
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(20) NOT NULL CHECK (identifier_type IN ('ip', 'user_id', 'api_key')),
    endpoint VARCHAR(200) NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    blocked_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_rate_limits IS 'API rate limiting for DDoS protection';

-- Indexes for soc_rate_limits
CREATE INDEX idx_soc_rate_limits_identifier ON soc_rate_limits(identifier);
CREATE INDEX idx_soc_rate_limits_endpoint ON soc_rate_limits(endpoint);
CREATE INDEX idx_soc_rate_limits_window_start ON soc_rate_limits(window_start);
CREATE INDEX idx_soc_rate_limits_blocked_until ON soc_rate_limits(blocked_until);

-- Create unique index for rate limit tracking
CREATE UNIQUE INDEX idx_soc_rate_limits_unique ON soc_rate_limits(identifier, identifier_type, endpoint, window_start);

-- ============================================================================
-- Table: soc_audit_logs
-- Description: Comprehensive audit logging with tamper-proof hash chain
-- ============================================================================
CREATE TABLE soc_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    previous_log_hash VARCHAR(64),
    log_hash VARCHAR(64) NOT NULL UNIQUE,
    user_id BIGINT REFERENCES soc_users(id) ON DELETE SET NULL,
    username VARCHAR(50),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    request_method VARCHAR(10),
    request_path VARCHAR(500),
    request_params TEXT,
    response_status INTEGER,
    old_values JSONB,
    new_values JSONB,
    changes JSONB,
    severity VARCHAR(20) NOT NULL DEFAULT 'info' CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    outcome VARCHAR(20) NOT NULL DEFAULT 'success' CHECK (outcome IN ('success', 'failure', 'partial')),
    session_id VARCHAR(100),
    correlation_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE soc_audit_logs IS 'Comprehensive audit log with tamper-proof hash chain';
COMMENT ON COLUMN soc_audit_logs.previous_log_hash IS 'Hash of previous log entry for chain verification';
COMMENT ON COLUMN soc_audit_logs.log_hash IS 'SHA-256 hash of this entry plus previous hash';

-- Indexes for soc_audit_logs
CREATE INDEX idx_soc_audit_logs_user_id ON soc_audit_logs(user_id);
CREATE INDEX idx_soc_audit_logs_username ON soc_audit_logs(username);
CREATE INDEX idx_soc_audit_logs_action ON soc_audit_logs(action);
CREATE INDEX idx_soc_audit_logs_resource_type ON soc_audit_logs(resource_type);
CREATE INDEX idx_soc_audit_logs_resource_id ON soc_audit_logs(resource_id);
CREATE INDEX idx_soc_audit_logs_severity ON soc_audit_logs(severity);
CREATE INDEX idx_soc_audit_logs_outcome ON soc_audit_logs(outcome);
CREATE INDEX idx_soc_audit_logs_created_at ON soc_audit_logs(created_at);
CREATE INDEX idx_soc_audit_logs_correlation_id ON soc_audit_logs(correlation_id);

-- Composite indexes for common queries
CREATE INDEX idx_soc_audit_logs_user_action ON soc_audit_logs(user_id, action, created_at DESC);
CREATE INDEX idx_soc_audit_logs_resource_action ON soc_audit_logs(resource_type, resource_id, created_at DESC);

-- ============================================================================
-- Trigger Function: calculate_audit_log_hash
-- Description: Creates a hash chain for tamper-proof audit logs
-- ============================================================================
CREATE OR REPLACE FUNCTION calculate_audit_log_hash()
RETURNS TRIGGER AS $$
DECLARE
    data_to_hash TEXT;
    calculated_hash VARCHAR(64);
BEGIN
    -- Concatenate all relevant data for hashing
    data_to_hash := COALESCE(NEW.previous_log_hash, '') ||
                    COALESCE(NEW.user_id::TEXT, '') ||
                    COALESCE(NEW.username, '') ||
                    NEW.action ||
                    NEW.resource_type ||
                    COALESCE(NEW.resource_id, '') ||
                    COALESCE(NEW.ip_address::TEXT, '') ||
                    COALESCE(NEW.request_method, '') ||
                    COALESCE(NEW.request_path, '') ||
                    COALESCE(NEW.response_status::TEXT, '') ||
                    COALESCE(NEW.old_values::TEXT, '') ||
                    COALESCE(NEW.new_values::TEXT, '') ||
                    NEW.severity ||
                    NEW.outcome ||
                    COALESCE(NEW.session_id, '') ||
                    COALESCE(NEW.correlation_id, '') ||
                    NEW.created_at::TEXT;

    -- Calculate SHA-256 hash
    calculated_hash := encode(digest(data_to_hash, 'sha256'), 'hex');

    -- Set the log hash
    NEW.log_hash := calculated_hash;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_audit_log_hash() IS 'Calculates SHA-256 hash for audit log chain integrity';

-- Create trigger for audit logs
CREATE TRIGGER trigger_calculate_audit_log_hash
    BEFORE INSERT ON soc_audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION calculate_audit_log_hash();

-- ============================================================================
-- Function: Update updated_at timestamp
-- Description: Automatically update updated_at column on row modification
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at on all relevant tables
CREATE TRIGGER trigger_soc_roles_updated_at BEFORE UPDATE ON soc_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_soc_menus_updated_at BEFORE UPDATE ON soc_menus
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_soc_users_updated_at BEFORE UPDATE ON soc_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_soc_system_config_updated_at BEFORE UPDATE ON soc_system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_soc_rate_limits_updated_at BEFORE UPDATE ON soc_rate_limits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Insert Default Data
-- ============================================================================

-- Insert default roles
INSERT INTO soc_roles (role_name, role_code, description, is_system) VALUES
('系统管理员', 'admin', '拥有系统所有权限的超级管理员', TRUE),
('普通用户', 'user', '具有业务操作权限的普通用户', TRUE),
('只读用户', 'readonly', '仅具有查看权限的用户', TRUE);

-- Insert default menu structure
INSERT INTO soc_menus (menu_name, menu_code, parent_id, menu_type, icon, path, component, sort_order) VALUES
-- Level 1 menus
('仪表板', 'dashboard', NULL, 'menu', 'Dashboard', '/dashboard', 'Dashboard.vue', 1),
('资产管理', 'assets', NULL, 'menu', 'Assets', '/assets', 'Assets.vue', 2),
('事件管理', 'incidents', NULL, 'menu', 'AlertTriangle', '/incidents', 'Incidents.vue', 3),
('告警管理', 'alerts', NULL, 'menu', 'Bell', '/alerts', 'Alerts.vue', 4),
('系统管理', 'system', NULL, 'directory', 'Settings', '/system', NULL, 5);

-- Get the ID of system management directory
INSERT INTO soc_menus (menu_name, menu_code, parent_id, menu_type, icon, path, component, sort_order)
SELECT '用户管理', 'system-users', id, 'menu', 'Users', '/system/users', 'system/Users.vue', 1
FROM soc_menus WHERE menu_code = 'system';

INSERT INTO soc_menus (menu_name, menu_code, parent_id, menu_type, icon, path, component, sort_order)
SELECT '角色管理', 'system-roles', id, 'menu', 'Shield', '/system/roles', 'system/Roles.vue', 2
FROM soc_menus WHERE menu_code = 'system';

INSERT INTO soc_menus (menu_name, menu_code, parent_id, menu_type, icon, path, component, sort_order)
SELECT '菜单管理', 'system-menus', id, 'menu', 'Menu', '/system/menus', 'system/Menus.vue', 3
FROM soc_menus WHERE menu_code = 'system';

INSERT INTO soc_menus (menu_name, menu_code, parent_id, menu_type, icon, path, component, sort_order)
SELECT '审计日志', 'system-audit', id, 'menu', 'FileText', '/system/audit', 'system/AuditLogs.vue', 4
FROM soc_menus WHERE menu_code = 'system';

INSERT INTO soc_menus (menu_name, menu_code, parent_id, menu_type, icon, path, component, sort_order)
SELECT '系统配置', 'system-config', id, 'menu', 'Settings', '/system/config', 'system/Config.vue', 5
FROM soc_menus WHERE menu_code = 'system';

-- Assign all menus to admin role
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM soc_roles r
CROSS JOIN soc_menus m
WHERE r.role_code = 'admin';

-- Assign business menus to user role (exclude system management)
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM soc_roles r
CROSS JOIN soc_menus m
WHERE r.role_code = 'user'
  AND m.menu_code NOT IN ('system', 'system-users', 'system-roles', 'system-menus', 'system-audit', 'system-config');

-- Assign business menus to readonly role (exclude system management)
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM soc_roles r
CROSS JOIN soc_menus m
WHERE r.role_code = 'readonly'
  AND m.menu_code NOT IN ('system', 'system-users', 'system-roles', 'system-menus', 'system-audit', 'system-config');

-- Insert default system configurations
INSERT INTO soc_system_config (config_key, config_value, config_type, description, is_public) VALUES
('system.name', 'AI-miniSOC', 'string', '系统名称', TRUE),
('system.version', '1.0.0', 'string', '系统版本', TRUE),
('system.logo_url', '/logo.png', 'string', '系统Logo URL', TRUE),
('security.password_min_length', '8', 'integer', '密码最小长度', FALSE),
('security.password_max_length', '128', 'integer', '密码最大长度', FALSE),
('security.password_require_uppercase', 'true', 'boolean', '密码是否需要大写字母', FALSE),
('security.password_require_lowercase', 'true', 'boolean', '密码是否需要小写字母', FALSE),
('security.password_require_number', 'true', 'boolean', '密码是否需要数字', FALSE),
('security.password_require_special', 'true', 'boolean', '密码是否需要特殊字符', FALSE),
('security.password_history_count', '5', 'integer', '记录历史密码数量（防止重复使用）', FALSE),
('security.password_expire_days', '90', 'integer', '密码过期天数（0表示永不过期）', FALSE),
('security.session_timeout_minutes', '60', 'integer', '会话超时时间（分钟）', FALSE),
('security.max_failed_login_attempts', '5', 'integer', '最大失败登录次数', FALSE),
('security.account_lockout_minutes', '30', 'integer', '账户锁定时长（分钟）', FALSE),
('security.jwt_secret', 'CHANGE_ME_IN_PRODUCTION', 'string', 'JWT签名密钥（生产环境必须修改）', FALSE),
('security.jwt_access_token_expire_minutes', '30', 'integer', 'JWT访问令牌过期时间（分钟）', FALSE),
('security.jwt_refresh_token_expire_days', '7', 'integer', 'JWT刷新令牌过期时间（天）', FALSE),
('rate_limit.enabled', 'true', 'boolean', '是否启用速率限制', FALSE),
('rate_limit.requests_per_minute', '60', 'integer', '每分钟请求限制', FALSE),
('rate_limit.requests_per_hour', '1000', 'integer', '每小时请求限制', FALSE),
('audit_log.retention_days', '90', 'integer', '审计日志保留天数', FALSE),
('audit_log.hash_chain_enabled', 'true', 'boolean', '是否启用审计日志哈希链', FALSE);

-- ============================================================================
-- Migration complete
-- ============================================================================
