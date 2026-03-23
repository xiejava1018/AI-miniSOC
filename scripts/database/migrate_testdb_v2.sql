-- ============================================================================
-- AI-miniSOC 数据库迁移脚本 (Bytebase兼容) - 简化版
-- 策略：先删除可能存在的冲突对象，再创建
-- ============================================================================

SET search_path TO public;

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 开始事务
BEGIN;

-- ============================================================================
-- 步骤 1: 创建自定义函数
-- ============================================================================

CREATE OR REPLACE FUNCTION update_soc_assets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 步骤 2: 创建缺失的表
-- ============================================================================

-- soc_incidents (先创建，其他表引用它)
CREATE TABLE IF NOT EXISTS soc_incidents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    severity character varying(20) DEFAULT 'medium'::character varying NOT NULL,
    wazuh_alert_id character varying(100),
    assigned_to character varying(255),
    created_by character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    resolved_at timestamp with time zone,
    resolution_notes text,
    ai_analysis_id uuid,
    CONSTRAINT soc_incidents_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_soc_incidents_status ON soc_incidents(status);
CREATE INDEX IF NOT EXISTS idx_soc_incidents_severity ON soc_incidents(severity);
CREATE INDEX IF NOT EXISTS idx_soc_incidents_assigned_to ON soc_incidents(assigned_to);
CREATE INDEX IF NOT EXISTS idx_soc_incidents_created_at ON soc_incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_soc_incidents_wazuh_alert_id ON soc_incidents(wazuh_alert_id);

-- soc_ai_analyses
CREATE TABLE IF NOT EXISTS soc_ai_analyses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    alert_id character varying(100) NOT NULL,
    alert_fingerprint character varying(100),
    explanation text,
    risk_assessment text,
    recommendations text,
    model_name character varying(100) NOT NULL,
    model_version character varying(50),
    tokens_used integer,
    cost numeric(10,4),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone,
    CONSTRAINT soc_ai_analyses_pkey PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS soc_ai_analyses_alert_id_key ON soc_ai_analyses(alert_id);
CREATE INDEX IF NOT EXISTS idx_soc_ai_analyses_alert_id ON soc_ai_analyses(alert_id);
CREATE INDEX IF NOT EXISTS idx_soc_ai_analyses_expires_at ON soc_ai_analyses(expires_at);
CREATE INDEX IF NOT EXISTS idx_soc_ai_analyses_fingerprint ON soc_ai_analyses(alert_fingerprint);

-- soc_asset_incidents
CREATE TABLE IF NOT EXISTS soc_asset_incidents (
    asset_id uuid NOT NULL,
    incident_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT soc_asset_incidents_pkey PRIMARY KEY (asset_id, incident_id)
);

CREATE INDEX IF NOT EXISTS idx_soc_asset_incidents_asset ON soc_asset_incidents(asset_id);
CREATE INDEX IF NOT EXISTS idx_soc_asset_incidents_incident ON soc_asset_incidents(incident_id);

-- soc_asset_tags
CREATE TABLE IF NOT EXISTS soc_asset_tags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    asset_id uuid NOT NULL,
    tag_key character varying(50) NOT NULL,
    tag_value character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT soc_asset_tags_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_soc_asset_tags_asset ON soc_asset_tags(asset_id);
CREATE INDEX IF NOT EXISTS idx_soc_asset_tags_key_value ON soc_asset_tags(tag_key, tag_value);

-- soc_audit_logs
CREATE SEQUENCE IF NOT EXISTS soc_audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS soc_audit_logs (
    id bigint NOT NULL DEFAULT nextval('soc_audit_logs_id_seq'::regclass),
    user_id bigint,
    username character varying(50) NOT NULL,
    action character varying(50) NOT NULL,
    resource_type character varying(50),
    resource_id bigint,
    resource_name character varying(200),
    old_values jsonb,
    new_values jsonb,
    ip_address character varying(45),
    user_agent text,
    session_id bigint,
    request_id character varying(36),
    status character varying(20),
    error_message text,
    log_hash character varying(64),
    prev_log_hash character varying(64),
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT soc_audit_logs_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE soc_audit_logs_id_seq OWNED BY soc_audit_logs.id;

-- soc_incident_timeline
CREATE TABLE IF NOT EXISTS soc_incident_timeline (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    incident_id uuid NOT NULL,
    action_type character varying(50) NOT NULL,
    action_data jsonb,
    created_by character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT soc_incident_timeline_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_soc_incident_timeline_incident ON soc_incident_timeline(incident_id);
CREATE INDEX IF NOT EXISTS idx_soc_incident_timeline_action_type ON soc_incident_timeline(action_type);
CREATE INDEX IF NOT EXISTS idx_soc_incident_timeline_created_at ON soc_incident_timeline(created_at DESC);

-- soc_password_history
CREATE SEQUENCE IF NOT EXISTS soc_password_history_id_seq
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS soc_password_history (
    id bigint NOT NULL DEFAULT nextval('soc_password_history_id_seq'::regclass),
    user_id bigint NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT soc_password_history_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE soc_password_history_id_seq OWNED BY soc_password_history.id;

-- soc_password_reset_tokens
CREATE SEQUENCE IF NOT EXISTS soc_password_reset_tokens_id_seq
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS soc_password_reset_tokens (
    id bigint NOT NULL DEFAULT nextval('soc_password_reset_tokens_id_seq'::regclass),
    user_id bigint NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT soc_password_reset_tokens_pkey PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS soc_password_reset_tokens_token_hash_key ON soc_password_reset_tokens(token_hash);

ALTER SEQUENCE soc_password_reset_tokens_id_seq OWNED BY soc_password_reset_tokens.id;

-- soc_rate_limits
CREATE SEQUENCE IF NOT EXISTS soc_rate_limits_id_seq
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS soc_rate_limits (
    id bigint NOT NULL DEFAULT nextval('soc_rate_limits_id_seq'::regclass),
    user_id bigint,
    ip_address character varying(45) NOT NULL,
    endpoint character varying(200) NOT NULL,
    request_count integer,
    window_start timestamp with time zone DEFAULT now(),
    blocked_until timestamp with time zone,
    CONSTRAINT soc_rate_limits_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE soc_rate_limits_id_seq OWNED BY soc_rate_limits.id;

-- soc_system_config
CREATE SEQUENCE IF NOT EXISTS soc_system_config_id_seq
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS soc_system_config (
    id bigint NOT NULL DEFAULT nextval('soc_system_config_id_seq'::regclass),
    category character varying(50) NOT NULL,
    key character varying(100) NOT NULL,
    value text,
    value_type character varying(20),
    is_encrypted boolean,
    description text,
    updated_by bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT soc_system_config_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE soc_system_config_id_seq OWNED BY soc_system_config.id;

-- soc_user_sessions
CREATE SEQUENCE IF NOT EXISTS soc_user_sessions_id_seq
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS soc_user_sessions (
    id bigint NOT NULL DEFAULT nextval('soc_user_sessions_id_seq'::regclass),
    user_id bigint NOT NULL,
    token_hash character varying(64) NOT NULL,
    refresh_token_hash character varying(64),
    ip_address character varying(45),
    user_agent character varying,
    login_at timestamp with time zone DEFAULT now(),
    logout_at timestamp with time zone,
    last_activity_at timestamp with time zone DEFAULT now(),
    is_active boolean,
    CONSTRAINT soc_user_sessions_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE soc_user_sessions_id_seq OWNED BY soc_user_sessions.id;

-- ============================================================================
-- 步骤 3: 修改现有表结构
-- ============================================================================

-- soc_asset_ports
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'soc_asset_ports' AND column_name = 'last_seen') THEN
        ALTER TABLE soc_asset_ports ADD COLUMN last_seen timestamp without time zone DEFAULT CURRENT_TIMESTAMP;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'soc_asset_ports' AND column_name = 'service_banner') THEN
        ALTER TABLE soc_asset_ports ADD COLUMN service_banner text;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'soc_asset_ports' AND column_name = 'vulnerability') THEN
        ALTER TABLE soc_asset_ports ADD COLUMN vulnerability text;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_ip_port ON soc_asset_ports(asset_ip, port);
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_protocol ON soc_asset_ports(protocol);
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_scan_time ON soc_asset_ports(scan_time);
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_service ON soc_asset_ports(service);

-- soc_assets
CREATE UNIQUE INDEX IF NOT EXISTS soc_assets_asset_ip_key ON soc_assets(asset_ip);
CREATE INDEX IF NOT EXISTS idx_soc_assets_criticality ON soc_assets(criticality);
CREATE INDEX IF NOT EXISTS idx_soc_assets_type ON soc_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_soc_assets_wazuh ON soc_assets(wazuh_agent_id);

DROP TRIGGER IF EXISTS trigger_update_soc_assets_updated_at ON soc_assets;
CREATE TRIGGER trigger_update_soc_assets_updated_at
    BEFORE UPDATE ON soc_assets
    FOR EACH ROW
    EXECUTE FUNCTION update_soc_assets_updated_at();

-- soc_menus
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'soc_menus' AND column_name = 'is_visible') THEN
        ALTER TABLE soc_menus ADD COLUMN is_visible boolean;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'soc_menus' AND column_name = 'updated_at') THEN
        ALTER TABLE soc_menus ADD COLUMN updated_at timestamp with time zone DEFAULT now();
    END IF;
END $$;

-- soc_roles
CREATE UNIQUE INDEX IF NOT EXISTS soc_roles_name_key ON soc_roles(name);

COMMIT;
