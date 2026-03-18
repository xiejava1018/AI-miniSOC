-- ============================================================================
-- AI-miniSOC 核心表创建脚本（MVP v0.1）
-- ============================================================================
-- 功能：创建剩余的核心业务表
-- 版本：v1.0
-- 日期：2026-03-18
--
-- 包含表：
--   1. soc_incidents - 事件表
--   2. soc_ai_analyses - AI分析缓存表
--   3. soc_asset_incidents - 资产-事件关联表
--   4. soc_asset_tags - 资产标签表
--   5. soc_incident_timeline - 事件时间线表
--
-- 设计原则：
--   - 所有表使用 soc_ 前缀
--   - 主键使用 UUID（与soc_assets保持一致）
--   - 时间戳使用 timestamptz（带时区）
--   - 完整的索引、约束、注释
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 事件表（soc_incidents）
-- ============================================================================

CREATE TABLE soc_incidents (
    -- 主键
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 基本信息
    title VARCHAR(255) NOT NULL,
    description TEXT,

    -- 状态和优先级
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    severity VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical', 'high', 'medium', 'low')),

    -- Wazuh关联
    wazuh_alert_id VARCHAR(100),

    -- 人员信息
    assigned_to VARCHAR(255),
    created_by VARCHAR(255) NOT NULL,

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,

    -- 解决方案
    resolution_notes TEXT,

    -- AI分析关联
    ai_analysis_id UUID
);

-- 添加表注释
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

-- 创建索引
CREATE INDEX idx_soc_incidents_status ON soc_incidents(status);
CREATE INDEX idx_soc_incidents_severity ON soc_incidents(severity);
CREATE INDEX idx_soc_incidents_created_at ON soc_incidents(created_at DESC);
CREATE INDEX idx_soc_incidents_wazuh_alert_id ON soc_incidents(wazuh_alert_id);
CREATE INDEX idx_soc_incidents_assigned_to ON soc_incidents(assigned_to);

-- ============================================================================
-- 2. AI分析缓存表（soc_ai_analyses）
-- ============================================================================

CREATE TABLE soc_ai_analyses (
    -- 主键
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 告警信息
    alert_id VARCHAR(100) UNIQUE NOT NULL,
    alert_fingerprint VARCHAR(100),

    -- AI分析结果
    explanation TEXT,
    risk_assessment TEXT,
    recommendations TEXT,

    -- 模型信息
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),

    -- 使用统计
    tokens_used INTEGER,
    cost DECIMAL(10, 4),

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ
);

-- 添加表注释
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

-- 创建索引
CREATE INDEX idx_soc_ai_analyses_alert_id ON soc_ai_analyses(alert_id);
CREATE INDEX idx_soc_ai_analyses_fingerprint ON soc_ai_analyses(alert_fingerprint);
CREATE INDEX idx_soc_ai_analyses_expires_at ON soc_ai_analyses(expires_at);

-- ============================================================================
-- 3. 资产-事件关联表（soc_asset_incidents）
-- ============================================================================

CREATE TABLE soc_asset_incidents (
    -- 复合主键
    asset_id UUID NOT NULL,
    incident_id UUID NOT NULL,

    -- 关联信息
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 主键约束
    PRIMARY KEY (asset_id, incident_id),

    -- 外键约束
    CONSTRAINT fk_asset_incidents_asset
        FOREIGN KEY (asset_id)
        REFERENCES soc_assets(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_asset_incidents_incident
        FOREIGN KEY (incident_id)
        REFERENCES soc_incidents(id)
        ON DELETE CASCADE
);

-- 添加表注释
COMMENT ON TABLE soc_asset_incidents IS '资产-事件关联表（多对多关系）';
COMMENT ON COLUMN soc_asset_incidents.asset_id IS '资产ID（外键 → soc_assets.id）';
COMMENT ON COLUMN soc_asset_incidents.incident_id IS '事件ID（外键 → soc_incidents.id）';
COMMENT ON COLUMN soc_asset_incidents.created_at IS '关联创建时间';

-- 创建索引
CREATE INDEX idx_soc_asset_incidents_asset ON soc_asset_incidents(asset_id);
CREATE INDEX idx_soc_asset_incidents_incident ON soc_asset_incidents(incident_id);

-- ============================================================================
-- 4. 资产标签表（soc_asset_tags）
-- ============================================================================

CREATE TABLE soc_asset_tags (
    -- 主键
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 关联资产
    asset_id UUID NOT NULL,

    -- 标签信息
    tag_key VARCHAR(50) NOT NULL,
    tag_value VARCHAR(100) NOT NULL,

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 唯一约束（每个资产每个标签键只能有一个值）
    CONSTRAINT uq_asset_tag_key UNIQUE (asset_id, tag_key),

    -- 外键约束
    CONSTRAINT fk_asset_tags_asset
        FOREIGN KEY (asset_id)
        REFERENCES soc_assets(id)
        ON DELETE CASCADE
);

-- 添加表注释
COMMENT ON TABLE soc_asset_tags IS '资产标签表 - 灵活的标签系统';
COMMENT ON COLUMN soc_asset_tags.id IS '主键（UUID）';
COMMENT ON COLUMN soc_asset_tags.asset_id IS '资产ID（外键 → soc_assets.id）';
COMMENT ON COLUMN soc_asset_tags.tag_key IS '标签键（如：environment, business_system）';
COMMENT ON COLUMN soc_asset_tags.tag_value IS '标签值（如：production, hr-system）';
COMMENT ON COLUMN soc_asset_tags.created_at IS '创建时间';

-- 创建索引
CREATE INDEX idx_soc_asset_tags_asset ON soc_asset_tags(asset_id);
CREATE INDEX idx_soc_asset_tags_key_value ON soc_asset_tags(tag_key, tag_value);

-- ============================================================================
-- 5. 事件时间线表（soc_incident_timeline）
-- ============================================================================

CREATE TABLE soc_incident_timeline (
    -- 主键
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 关联事件
    incident_id UUID NOT NULL,

    -- 操作信息
    action_type VARCHAR(50) NOT NULL,
    action_data JSONB,

    -- 操作人
    created_by VARCHAR(255) NOT NULL,

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 外键约束
    CONSTRAINT fk_incident_timeline_incident
        FOREIGN KEY (incident_id)
        REFERENCES soc_incidents(id)
        ON DELETE CASCADE
);

-- 添加表注释
COMMENT ON TABLE soc_incident_timeline IS '事件时间线表 - 记录事件处理过程';
COMMENT ON COLUMN soc_incident_timeline.id IS '主键（UUID）';
COMMENT ON COLUMN soc_incident_timeline.incident_id IS '事件ID（外键 → soc_incidents.id）';
COMMENT ON COLUMN soc_incident_timeline.action_type IS '操作类型：status_change/note/assignment等';
COMMENT ON COLUMN soc_incident_timeline.action_data IS '操作详细数据（JSON格式）';
COMMENT ON COLUMN soc_incident_timeline.created_by IS '操作人';
COMMENT ON COLUMN soc_incident_timeline.created_at IS '操作时间';

-- 创建索引
CREATE INDEX idx_soc_incident_timeline_incident ON soc_incident_timeline(incident_id);
CREATE INDEX idx_soc_incident_timeline_action_type ON soc_incident_timeline(action_type);
CREATE INDEX idx_soc_incident_timeline_created_at ON soc_incident_timeline(created_at DESC);

-- ============================================================================
-- 6. 添加AI分析表的外键约束
-- ============================================================================

-- 修改soc_incidents表，添加对soc_ai_analyses的外键
ALTER TABLE soc_incidents
ADD CONSTRAINT fk_incidents_ai_analysis
FOREIGN KEY (ai_analysis_id)
REFERENCES soc_ai_analyses(id)
ON DELETE SET NULL;

-- ============================================================================
-- 7. 验证结果
-- ============================================================================

DO $$
DECLARE
    table_count INTEGER;
    table_names TEXT[];
BEGIN
    -- 统计新创建的表
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN (
        'soc_incidents',
        'soc_ai_analyses',
        'soc_asset_incidents',
        'soc_asset_tags',
        'soc_incident_timeline'
    );

    -- 获取表名列表
    SELECT ARRAY(
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE 'soc_%'
        ORDER BY table_name
    ) INTO table_names;

    RAISE NOTICE '✅ MVP v0.1 核心表创建完成！';
    RAISE NOTICE '   新创建表数: %', table_count;
    RAISE NOTICE '   所有soc_表: %', ARRAY_TO_STRING(table_names, ', ');
END $$;

-- 提交事务
COMMIT;

-- ============================================================================
-- 完成
-- ============================================================================
