-- ============================================================================
-- AI-miniSOC 审计日志表创建脚本
-- ============================================================================
-- 功能：创建审计日志表
-- 版本：v1.0
-- 日期：2026-03-23
--
-- 设计原则：
--   - 使用 soc_ 前缀
--   - 主键使用 BIGINT 自增
--   - 时间戳使用 TIMESTAMPTZ（带时区）
--   - JSONB 用于存储变更数据
--   - 完整的索引、约束、注释
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 审计日志表（soc_audit_logs）
-- ============================================================================

CREATE TABLE IF NOT EXISTS soc_audit_logs (
    -- 主键
    id BIGSERIAL PRIMARY KEY,

    -- 用户信息
    user_id BIGINT,
    username VARCHAR(50) NOT NULL,

    -- 操作信息
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id BIGINT,
    resource_name VARCHAR(200),

    -- 变更数据（JSONB格式存储）
    old_values JSONB,
    new_values JSONB,

    -- 请求信息
    ip_address VARCHAR(45),
    user_agent TEXT,
    session_id BIGINT,
    request_id VARCHAR(36),

    -- 状态信息
    status VARCHAR(20) NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'failure')),
    error_message TEXT,

    -- 完整性校验（用于防止日志被篡改）
    log_hash VARCHAR(64),
    prev_log_hash VARCHAR(64),

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 外键约束
    CONSTRAINT fk_audit_logs_user
        FOREIGN KEY (user_id)
        REFERENCES soc_users(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_audit_logs_session
        FOREIGN KEY (session_id)
        REFERENCES soc_user_sessions(id)
        ON DELETE SET NULL
);

-- 添加表注释
COMMENT ON TABLE soc_audit_logs IS '审计日志表 - 记录所有用户操作和系统事件';
COMMENT ON COLUMN soc_audit_logs.id IS '主键（自增BIGINT）';
COMMENT ON COLUMN soc_audit_logs.user_id IS '用户ID（外键关联soc_users）';
COMMENT ON COLUMN soc_audit_logs.username IS '用户名（冗余字段，便于查询）';
COMMENT ON COLUMN soc_audit_logs.action IS '操作类型：LOGIN/LOGOUT/CREATE/UPDATE/DELETE/QUERY/EXPORT';
COMMENT ON COLUMN soc_audit_logs.resource_type IS '资源类型：user/role/menu/asset/incident/alert';
COMMENT ON COLUMN soc_audit_logs.resource_id IS '资源ID';
COMMENT ON COLUMN soc_audit_logs.resource_name IS '资源名称（便于显示）';
COMMENT ON COLUMN soc_audit_logs.old_values IS '变更前的数据（JSONB格式）';
COMMENT ON COLUMN soc_audit_logs.new_values IS '变更后的数据（JSONB格式）';
COMMENT ON COLUMN soc_audit_logs.ip_address IS '客户端IP地址（支持IPv6）';
COMMENT ON COLUMN soc_audit_logs.user_agent IS '客户端用户代理（浏览器信息）';
COMMENT ON COLUMN soc_audit_logs.session_id IS '会话ID（外键关联soc_user_sessions）';
COMMENT ON COLUMN soc_audit_logs.request_id IS '请求ID（用于追踪）';
COMMENT ON COLUMN soc_audit_logs.status IS '操作状态：success/failure';
COMMENT ON COLUMN soc_audit_logs.error_message IS '错误信息（失败时记录）';
COMMENT ON COLUMN soc_audit_logs.log_hash IS '当前日志的哈希值（SHA256，用于完整性校验）';
COMMENT ON COLUMN soc_audit_logs.prev_log_hash IS '上一条日志的哈希值（形成链式结构）';
COMMENT ON COLUMN soc_audit_logs.created_at IS '创建时间';

-- 创建索引（优化查询性能）
CREATE INDEX idx_audit_logs_user_id ON soc_audit_logs(user_id);
CREATE INDEX idx_audit_logs_username ON soc_audit_logs(username);
CREATE INDEX idx_audit_logs_action ON soc_audit_logs(action);
CREATE INDEX idx_audit_logs_resource_type ON soc_audit_logs(resource_type);
CREATE INDEX idx_audit_logs_status ON soc_audit_logs(status);
CREATE INDEX idx_audit_logs_created_at ON soc_audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_resource_id ON soc_audit_logs(resource_id);
CREATE INDEX idx_audit_logs_session_id ON soc_audit_logs(session_id);

-- 复合索引（常用查询组合）
CREATE INDEX idx_audit_logs_user_action ON soc_audit_logs(user_id, action);
CREATE INDEX idx_audit_logs_resource_action ON soc_audit_logs(resource_type, resource_id, action);
CREATE INDEX idx_audit_logs_date_range ON soc_audit_logs(created_at DESC, status);

-- GIN索引（用于JSONB查询）
CREATE INDEX idx_audit_logs_old_values ON soc_audit_logs USING GIN (old_values);
CREATE INDEX idx_audit_logs_new_values ON soc_audit_logs USING GIN (new_values);

-- ============================================================================
-- 插入初始测试数据（可选）
-- ============================================================================

-- 插入一些示例审计日志
INSERT INTO soc_audit_logs (user_id, username, action, resource_type, resource_id, resource_name, ip_address, status, created_at)
VALUES
    (1, 'admin', 'LOGIN', NULL, NULL, NULL, '192.168.0.1', 'success', NOW() - INTERVAL '1 day'),
    (1, 'admin', 'CREATE', 'user', 2, 'testuser', '192.168.0.1', 'success', NOW() - INTERVAL '12 hours'),
    (2, 'testuser', 'LOGIN', NULL, NULL, NULL, '192.168.0.2', 'success', NOW() - INTERVAL '6 hours'),
    (1, 'admin', 'UPDATE', 'user', 2, 'testuser', '192.168.0.1', 'success', NOW() - INTERVAL '3 hours'),
    (2, 'testuser', 'QUERY', 'asset', NULL, NULL, '192.168.0.2', 'success', NOW() - INTERVAL '1 hour')
ON CONFLICT DO NOTHING;

-- 提交事务
COMMIT;

-- ============================================================================
-- 验证
-- ============================================================================

-- 查看表结构
\d soc_audit_logs

-- 查看索引
\di *audit_logs*

-- 查看测试数据
SELECT id, username, action, resource_type, status, created_at
FROM soc_audit_logs
ORDER BY created_at DESC
LIMIT 10;

-- 统计日志数量
SELECT COUNT(*) as total_logs FROM soc_audit_logs;
