-- ============================================================================
-- AI-miniSOC 数据库迁移脚本 (Bytebase兼容)
-- 源数据库: AI-miniSOC-db
-- 目标数据库: AI-miniSOC-testdb
-- 生成时间: 2026-03-22
-- 
-- 说明: 同步目标数据库的结构与源数据库一致
-- 警告: 执行前请备份目标数据库！
--
-- Bytebase兼容性说明:
-- - 不使用 DROP IF EXISTS
-- - 不使用 psql 元命令
-- - 明确的事务控制
-- ============================================================================

SET search_path TO public;

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 开始事务
BEGIN;

-- ============================================================================
-- 步骤 1: 创建缺失的自定义函数
-- ============================================================================

-- 创建函数: update_soc_assets_updated_at
CREATE FUNCTION update_soc_assets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 步骤 2: 创建源数据库独有的表
-- ============================================================================

-- 表: soc_ai_analyses
CREATE TABLE soc_ai_analyses (
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
    CONSTRAINT soc_ai_analyses_alert_id_key UNIQUE (alert_id),
    CONSTRAINT soc_ai_analyses_pkey PRIMARY KEY (id)
);

COMMENT ON TABLE soc_ai_analyses IS 'AI分析缓存表 - 避免重复调用AI模型API';
COMMENT ON COLUMN soc_ai_analyses.id IS '主键（UUID）';
COMMENT ON COLUMN soc_ai_analyses.alert_id IS 'Wazuh告警ID（唯一）';
COMMENT ON COLUMN soc_ai_analyses.alert_fingerprint IS '告警指纹（相同类型可复用）';
COMMENT ON COLUMN soc_ai_analyses.explanation IS 'AI解释（人话翻译）';
COMMENT ON COLUMN soc_ai_analyses.risk_assessment IS '风险评估';
COMMENT ON COLUMN soc_ai_analyses.recommendations IS '处置建议';
COMMENT ON COLUMN soc_ai_analyses.model_name IS '使用的AI模型名称';
COMMENT ON COLUMN soc_ai_analyses.model_version IS '模型版本';
COMMENT ON COLUMN soc_ai_analyses.tokens_used IS '消耗的token数量';
COMMENT ON COLUMN soc_ai_analyses.cost IS '成本（人民币）';
COMMENT ON COLUMN soc_ai_analyses.created_at IS '创建时间';
COMMENT ON COLUMN soc_ai_analyses.expires_at IS '缓存过期时间';

CREATE INDEX idx_soc_ai_analyses_alert_id ON soc_ai_analyses(alert_id);
CREATE INDEX idx_soc_ai_analyses_expires_at ON soc_ai_analyses(expires_at);
CREATE INDEX idx_soc_ai_analyses_fingerprint ON soc_ai_analyses(alert_fingerprint);

-- 表: soc_asset_incidents
CREATE TABLE soc_asset_incidents (
    asset_id uuid NOT NULL,
    incident_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT soc_asset_incidents_pkey PRIMARY KEY (asset_id, incident_id),
    CONSTRAINT fk_asset_incidents_asset FOREIGN KEY (asset_id) REFERENCES soc_assets(id) ON DELETE CASCADE,
    CONSTRAINT fk_asset_incidents_incident FOREIGN KEY (incident_id) REFERENCES soc_incidents(id) ON DELETE CASCADE
);

COMMENT ON TABLE soc_asset_incidents IS '资产-事件关联表（多对多关系）';
COMMENT ON COLUMN soc_asset_incidents.asset_id IS '资产ID（外键 → soc_assets.id）';
COMMENT ON COLUMN soc_asset_incidents.incident_id IS '事件ID（外键 → soc_incidents.id）';
COMMENT ON COLUMN soc_asset_incidents.created_at IS '关联创建时间';

CREATE INDEX idx_soc_asset_incidents_asset ON soc_asset_incidents(asset_id);
CREATE INDEX idx_soc_asset_incidents_incident ON soc_asset_incidents(incident_id);

-- 表: soc_asset_tags
CREATE TABLE soc_asset_tags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    asset_id uuid NOT NULL,
    tag_key character varying(50) NOT NULL,
    tag_value character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT soc_asset_tags_pkey PRIMARY KEY (id),
    CONSTRAINT uq_asset_tag_key UNIQUE (asset_id, tag_key),
    CONSTRAINT fk_asset_tags_asset FOREIGN KEY (asset_id) REFERENCES soc_assets(id) ON DELETE CASCADE
);

COMMENT ON TABLE soc_asset_tags IS '资产标签表 - 灵活的标签系统';
COMMENT ON COLUMN soc_asset_tags.id IS '主键（UUID）';
COMMENT ON COLUMN soc_asset_tags.asset_id IS '资产ID（外键 → soc_assets.id）';
COMMENT ON COLUMN soc_asset_tags.tag_key IS '标签键（如：environment, business_system）';
COMMENT ON COLUMN soc_asset_tags.tag_value IS '标签值（如：production, hr-system）';
COMMENT ON COLUMN soc_asset_tags.created_at IS '创建时间';

CREATE INDEX idx_soc_asset_tags_asset ON soc_asset_tags(asset_id);
CREATE INDEX idx_soc_asset_tags_key_value ON soc_asset_tags(tag_key, tag_value);

-- 表: soc_audit_logs
CREATE SEQUENCE soc_audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE soc_audit_logs (
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
    CONSTRAINT soc_audit_logs_pkey PRIMARY KEY (id),
    CONSTRAINT soc_audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES soc_users(id),
    CONSTRAINT soc_audit_logs_session_id_fkey FOREIGN KEY (session_id) REFERENCES soc_user_sessions(id)
);

ALTER SEQUENCE soc_audit_logs_id_seq OWNED BY soc_audit_logs.id;

-- 表: soc_incident_timeline
CREATE TABLE soc_incident_timeline (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    incident_id uuid NOT NULL,
    action_type character varying(50) NOT NULL,
    action_data jsonb,
    created_by character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT soc_incident_timeline_pkey PRIMARY KEY (id),
    CONSTRAINT fk_incident_timeline_incident FOREIGN KEY (incident_id) REFERENCES soc_incidents(id) ON DELETE CASCADE
);

COMMENT ON TABLE soc_incident_timeline IS '事件时间线表 - 记录事件处理过程';
COMMENT ON COLUMN soc_incident_timeline.id IS '主键（UUID）';
COMMENT ON COLUMN soc_incident_timeline.incident_id IS '事件ID（外键 → soc_incidents.id）';
COMMENT ON COLUMN soc_incident_timeline.action_type IS '操作类型：status_change/note/assignment等';
COMMENT ON COLUMN soc_incident_timeline.action_data IS '操作详细数据（JSON格式）';
COMMENT ON COLUMN soc_incident_timeline.created_by IS '操作人';
COMMENT ON COLUMN soc_incident_timeline.created_at IS '操作时间';

CREATE INDEX idx_soc_incident_timeline_incident ON soc_incident_timeline(incident_id);
CREATE INDEX idx_soc_incident_timeline_action_type ON soc_incident_timeline(action_type);
CREATE INDEX idx_soc_incident_timeline_created_at ON soc_incident_timeline(created_at DESC);

-- 表: soc_incidents
CREATE TABLE soc_incidents (
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
    CONSTRAINT soc_incidents_pkey PRIMARY KEY (id),
    CONSTRAINT soc_incidents_severity_check CHECK (((severity)::text = ANY ((ARRAY['critical'::character varying, 'high'::character varying, 'medium'::character varying, 'low'::character varying])::text[]))),
    CONSTRAINT soc_incidents_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'in_progress'::character varying, 'resolved'::character varying, 'closed'::character varying])::text[]))),
    CONSTRAINT fk_incidents_ai_analysis FOREIGN KEY (ai_analysis_id) REFERENCES soc_ai_analyses(id) ON DELETE SET NULL
);

COMMENT ON TABLE soc_incidents IS '安全事件表 - 记录和管理安全事件';
COMMENT ON COLUMN soc_incidents.id IS '主键（UUID）';
COMMENT ON COLUMN soc_incidents.title IS '事件标题';
COMMENT ON COLUMN soc_incidents.description IS '事件详细描述';
COMMENT ON COLUMN soc_incidents.status IS '事件状态：open/in_progress/resolved/closed';
COMMENT ON COLUMN soc_incidents.severity IS '严重程度：critical/high/medium/low';
COMMENT ON COLUMN soc_incidents.wazuh_alert_id IS '关联的Wazuh告警ID';
COMMENT ON COLUMN soc_incidents.assigned_to IS '事件负责人';
COMMENT ON COLUMN soc_incidents.created_by IS '事件创建人';
COMMENT ON COLUMN soc_incidents.created_at IS '创建时间';
COMMENT ON COLUMN soc_incidents.updated_at IS '最后更新时间';
COMMENT ON COLUMN soc_incidents.resolved_at IS '解决时间';
COMMENT ON COLUMN soc_incidents.resolution_notes IS '解决方案说明';
COMMENT ON COLUMN soc_incidents.ai_analysis_id IS '关联的AI分析ID';

CREATE INDEX idx_soc_incidents_status ON soc_incidents(status);
CREATE INDEX idx_soc_incidents_severity ON soc_incidents(severity);
CREATE INDEX idx_soc_incidents_assigned_to ON soc_incidents(assigned_to);
CREATE INDEX idx_soc_incidents_created_at ON soc_incidents(created_at DESC);
CREATE INDEX idx_soc_incidents_wazuh_alert_id ON soc_incidents(wazuh_alert_id);

-- 表: soc_password_history
CREATE SEQUENCE soc_password_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE soc_password_history (
    id bigint NOT NULL DEFAULT nextval('soc_password_history_id_seq'::regclass),
    user_id bigint NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT soc_password_history_pkey PRIMARY KEY (id),
    CONSTRAINT soc_password_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES soc_users(id) ON DELETE CASCADE
);

ALTER SEQUENCE soc_password_history_id_seq OWNED BY soc_password_history.id;

-- 表: soc_password_reset_tokens
CREATE SEQUENCE soc_password_reset_tokens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE soc_password_reset_tokens (
    id bigint NOT NULL DEFAULT nextval('soc_password_reset_tokens_id_seq'::regclass),
    user_id bigint NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT soc_password_reset_tokens_pkey PRIMARY KEY (id),
    CONSTRAINT soc_password_reset_tokens_token_hash_key UNIQUE (token_hash),
    CONSTRAINT soc_password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES soc_users(id) ON DELETE CASCADE
);

ALTER SEQUENCE soc_password_reset_tokens_id_seq OWNED BY soc_password_reset_tokens.id;

-- 表: soc_rate_limits
CREATE SEQUENCE soc_rate_limits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE soc_rate_limits (
    id bigint NOT NULL DEFAULT nextval('soc_rate_limits_id_seq'::regclass),
    user_id bigint,
    ip_address character varying(45) NOT NULL,
    endpoint character varying(200) NOT NULL,
    request_count integer,
    window_start timestamp with time zone DEFAULT now(),
    blocked_until timestamp with time zone,
    CONSTRAINT soc_rate_limits_pkey PRIMARY KEY (id),
    CONSTRAINT soc_rate_limits_user_id_fkey FOREIGN KEY (user_id) REFERENCES soc_users(id)
);

ALTER SEQUENCE soc_rate_limits_id_seq OWNED BY soc_rate_limits.id;

-- 表: soc_system_config
CREATE SEQUENCE soc_system_config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE soc_system_config (
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
    CONSTRAINT soc_system_config_pkey PRIMARY KEY (id),
    CONSTRAINT soc_system_config_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES soc_users(id)
);

ALTER SEQUENCE soc_system_config_id_seq OWNED BY soc_system_config.id;

-- 表: soc_user_sessions
CREATE SEQUENCE soc_user_sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE soc_user_sessions (
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
    CONSTRAINT soc_user_sessions_pkey PRIMARY KEY (id),
    CONSTRAINT soc_user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES soc_users(id) ON DELETE CASCADE
);

ALTER SEQUENCE soc_user_sessions_id_seq OWNED BY soc_user_sessions.id;

-- ============================================================================
-- 步骤 3: 同步共同表的结构
-- ============================================================================

-- 表: soc_asset_ports
ALTER TABLE soc_asset_ports ADD COLUMN last_seen timestamp without time zone DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE soc_asset_ports ADD COLUMN service_banner text;
ALTER TABLE soc_asset_ports ADD COLUMN vulnerability text;
ALTER TABLE soc_asset_ports ALTER COLUMN asset_ip TYPE inet USING asset_ip::inet;

CREATE INDEX idx_soc_asset_ports_ip_port ON soc_asset_ports(asset_ip, port);
CREATE INDEX idx_soc_asset_ports_protocol ON soc_asset_ports(protocol);
CREATE INDEX idx_soc_asset_ports_scan_time ON soc_asset_ports(scan_time);
CREATE INDEX idx_soc_asset_ports_service ON soc_asset_ports(service);
CREATE INDEX idx_soc_asset_ports_state ON soc_asset_ports(state);

COMMENT ON COLUMN soc_asset_ports.protocol IS '协议类型：tcp/udp';
COMMENT ON COLUMN soc_asset_ports.asset_ip IS '关联的资产IP（INET类型，与soc_assets保持一致）';
COMMENT ON COLUMN soc_asset_ports.port IS '端口号';
COMMENT ON COLUMN soc_asset_ports.service IS '服务名称（如：ssh, http, mysql）';
COMMENT ON COLUMN soc_asset_ports.version IS '服务版本号';
COMMENT ON COLUMN soc_asset_ports.scan_time IS '扫描时间';
COMMENT ON COLUMN soc_asset_ports.vulnerability IS '已知CVE漏洞信息（逗号分隔）';
COMMENT ON COLUMN soc_asset_ports.last_seen IS '最后检测到该端口开放的时间';
COMMENT ON COLUMN soc_asset_ports.service_banner IS '服务指纹/特征信息（用于服务识别）';
COMMENT ON COLUMN soc_asset_ports.state IS '端口状态：open/closed/filtered';
COMMENT ON TABLE soc_asset_ports IS '资产端口表 - 存储资产开放端口和服务信息';

-- 表: soc_assets
ALTER TABLE soc_assets ADD CONSTRAINT soc_assets_asset_ip_key UNIQUE (asset_ip);
ALTER TABLE soc_assets ADD CONSTRAINT soc_assets_asset_type_check CHECK (((asset_type)::text = ANY ((ARRAY['server'::character varying, 'workstation'::character varying, 'printer'::character varying, 'router'::character varying, 'switch'::character varying, 'nas'::character varying, 'firewall'::character varying, 'other'::character varying])::text[])));
ALTER TABLE soc_assets ADD CONSTRAINT soc_assets_criticality_check CHECK (((criticality)::text = ANY ((ARRAY['core'::character varying, 'important'::character varying, 'normal'::character varying])::text[])));

CREATE INDEX idx_soc_assets_criticality ON soc_assets(criticality);
CREATE INDEX idx_soc_assets_type ON soc_assets(asset_type);
CREATE INDEX idx_soc_assets_wazuh ON soc_assets(wazuh_agent_id);

CREATE TRIGGER trigger_update_soc_assets_updated_at
    BEFORE UPDATE ON soc_assets
    FOR EACH ROW
    EXECUTE FUNCTION update_soc_assets_updated_at();

COMMENT ON COLUMN soc_assets.name IS '资产名称';
COMMENT ON COLUMN soc_assets.mac_address IS 'MAC地址（用于设备识别）';
COMMENT ON COLUMN soc_assets.business_unit IS '所属业务单元/部门';
COMMENT ON COLUMN soc_assets.asset_ip IS '资产IP地址（PostgreSQL INET类型）';
COMMENT ON COLUMN soc_assets.criticality IS '重要性等级：critical/high/medium/low';
COMMENT ON COLUMN soc_assets.wazuh_agent_id IS '关联的Wazuh Agent ID（用于告警关联）';
COMMENT ON COLUMN soc_assets.updated_at IS '资产信息最后更新时间';
COMMENT ON COLUMN soc_assets.owner IS '资产负责人';
COMMENT ON COLUMN soc_assets.asset_type IS '资产类型：server/workstation/printer/router/switch/nas/firewall/other';
COMMENT ON TABLE soc_assets IS '安全资产表 - AI-miniSOC核心资产表，整合网络扫描和手动管理功能';
COMMENT ON COLUMN soc_assets.asset_description IS '资产描述（详细信息）';
COMMENT ON COLUMN soc_assets.asset_status IS '在线状态：新发现/在线/离线/已删除';
COMMENT ON COLUMN soc_assets.id IS '资产唯一标识（UUID格式）';

-- 表: soc_menus
ALTER TABLE soc_menus ADD COLUMN is_visible boolean;
ALTER TABLE soc_menus ADD COLUMN updated_at timestamp with time zone DEFAULT now();
ALTER TABLE soc_menus ALTER COLUMN parent_id TYPE bigint USING parent_id::bigint;
ALTER TABLE soc_menus ALTER COLUMN created_at TYPE timestamp with time zone USING created_at::timestamp with time zone;
ALTER TABLE soc_menus ALTER COLUMN id TYPE bigint USING id::bigint;
ALTER TABLE soc_menus ALTER COLUMN path SET NOT NULL;
ALTER TABLE soc_menus ALTER COLUMN sort_order DROP DEFAULT;
ALTER TABLE soc_menus ALTER COLUMN created_at SET DEFAULT now();

-- 表: soc_role_menus
ALTER TABLE soc_role_menus ALTER COLUMN role_id TYPE bigint USING role_id::bigint;
ALTER TABLE soc_role_menus ALTER COLUMN menu_id TYPE bigint USING menu_id::bigint;
ALTER TABLE soc_role_menus ALTER COLUMN role_id SET NOT NULL;
ALTER TABLE soc_role_menus ALTER COLUMN menu_id SET NOT NULL;

-- 表: soc_roles
ALTER TABLE soc_roles ALTER COLUMN name TYPE character varying(50) USING name::character varying(50);
ALTER TABLE soc_roles ALTER COLUMN updated_at TYPE timestamp with time zone USING updated_at::timestamp with time zone;
ALTER TABLE soc_roles ALTER COLUMN created_at TYPE timestamp with time zone USING created_at::timestamp with time zone;
ALTER TABLE soc_roles ALTER COLUMN id TYPE bigint USING id::bigint;
ALTER TABLE soc_roles ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE soc_roles ALTER COLUMN is_system DROP DEFAULT;
ALTER TABLE soc_roles ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE soc_roles ADD CONSTRAINT soc_roles_name_key UNIQUE (name);

CREATE UNIQUE INDEX soc_roles_name_key ON soc_roles(name);

-- 表: soc_users
ALTER TABLE soc_users ALTER COLUMN last_login TYPE timestamp with time zone USING last_login::timestamp with time zone;
ALTER TABLE soc_users ALTER COLUMN updated_at TYPE timestamp with time zone USING updated_at::timestamp with time zone;
ALTER TABLE soc_users ALTER COLUMN status TYPE character varying(20) USING status::character varying(20);
ALTER TABLE soc_users ALTER COLUMN created_at TYPE timestamp with time zone USING created_at::timestamp with time zone;
ALTER TABLE soc_users ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE soc_users ALTER COLUMN status DROP DEFAULT;
ALTER TABLE soc_users ALTER COLUMN is_superuser DROP DEFAULT;
ALTER TABLE soc_users ALTER COLUMN created_at SET DEFAULT now();

-- ============================================================================
-- 提交事务
-- ============================================================================

-- 提交所有变更
COMMIT;
