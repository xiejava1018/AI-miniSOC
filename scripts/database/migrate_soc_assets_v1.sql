-- AI-miniSOC 数据库表优化脚本
-- 功能：扩展现有soc_assets表，符合MVP v0.1需求
-- 作者：Claude
-- 日期：2026-03-18
-- 版本：v1.0

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- =====================================================
-- 1. 添加新字段
-- =====================================================

ALTER TABLE soc_assets
    -- 添加资产名称
    ADD COLUMN IF NOT EXISTS name VARCHAR(255),

    -- 添加MAC地址
    ADD COLUMN IF NOT EXISTS mac_address MACADDR,

    -- 添加资产类型（带默认值）
    ADD COLUMN IF NOT EXISTS asset_type VARCHAR(50) DEFAULT 'other',

    -- 添加重要性等级（带默认值）
    ADD COLUMN IF NOT EXISTS criticality VARCHAR(20) DEFAULT 'medium',

    -- 添加负责人
    ADD COLUMN IF NOT EXISTS owner VARCHAR(255),

    -- 添加业务单元
    ADD COLUMN IF NOT EXISTS business_unit VARCHAR(255),

    -- 添加Wazuh Agent关联
    ADD COLUMN IF NOT EXISTS wazuh_agent_id VARCHAR(100) UNIQUE,

    -- 添加更新时间戳
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- =====================================================
-- 2. 添加约束
-- =====================================================

-- 资产类型约束
ALTER TABLE soc_assets
    DROP CONSTRAINT IF EXISTS soc_assets_asset_type_check,
    ADD CONSTRAINT soc_assets_asset_type_check
    CHECK (asset_type IN (
        'server',           -- 服务器
        'workstation',      -- 工作站
        'printer',          -- 打印机
        'router',           -- 路由器
        'switch',           -- 交换机
        'nas',              -- 网络存储
        'firewall',         -- 防火墙
        'other'             -- 其他
    ));

-- 重要性等级约束
ALTER TABLE soc_assets
    DROP CONSTRAINT IF EXISTS soc_assets_criticality_check,
    ADD CONSTRAINT soc_assets_criticality_check
    CHECK (criticality IN (
        'critical',         -- 关键资产
        'high',             -- 重要资产
        'medium',           -- 一般资产
        'low'               -- 低优先级
    ));

-- =====================================================
-- 3. 修改IP字段类型为INET（PostgreSQL原生IP类型）
-- =====================================================

ALTER TABLE soc_assets
    ALTER COLUMN asset_ip TYPE INET USING asset_ip::INET;

-- =====================================================
-- 4. 迁移现有数据到name字段
-- =====================================================

UPDATE soc_assets
SET name = COALESCE(asset_description, '未命名资产')
WHERE name IS NULL OR name = '';

-- =====================================================
-- 5. 创建索引
-- =====================================================

-- IP地址索引（如果不存在）
CREATE INDEX IF NOT EXISTS idx_soc_assets_ip ON soc_assets(asset_ip);

-- Wazuh Agent索引
CREATE INDEX IF NOT EXISTS idx_soc_assets_wazuh ON soc_assets(wazuh_agent_id);

-- 资产类型索引
CREATE INDEX IF NOT EXISTS idx_soc_assets_type ON soc_assets(asset_type);

-- 重要性等级索引
CREATE INDEX IF NOT EXISTS idx_soc_assets_criticality ON soc_assets(criticality);

-- 状态索引
CREATE INDEX IF NOT EXISTS idx_soc_assets_status ON soc_assets(asset_status);

-- =====================================================
-- 6. 添加表和字段注释
-- =====================================================

COMMENT ON TABLE soc_assets IS '安全资产表 - AI-miniSOC核心资产表，整合网络扫描和手动管理功能';

COMMENT ON COLUMN soc_assets.id IS '资产唯一标识（UUID格式）';
COMMENT ON COLUMN soc_assets.asset_ip IS '资产IP地址（PostgreSQL INET类型）';
COMMENT ON COLUMN soc_assets.name IS '资产名称';
COMMENT ON COLUMN soc_assets.asset_description IS '资产描述（原字段，保留用于扩展信息）';
COMMENT ON COLUMN soc_assets.mac_address IS 'MAC地址（用于设备识别）';
COMMENT ON COLUMN soc_assets.asset_type IS '资产类型：server/workstation/printer/router/switch/nas/firewall/other';
COMMENT ON COLUMN soc_assets.criticality IS '重要性等级：critical/high/medium/low';
COMMENT ON COLUMN soc_assets.asset_status IS '在线状态：新发现/在线/离线/已删除';
COMMENT ON COLUMN soc_assets.owner IS '资产负责人';
COMMENT ON COLUMN soc_assets.business_unit IS '所属业务单元/部门';
COMMENT ON COLUMN soc_assets.wazuh_agent_id IS '关联的Wazuh Agent ID（用于告警关联）';
COMMENT ON COLUMN soc_assets.status_updated_at IS '状态最后更新时间';
COMMENT ON COLUMN soc_assets.created_at IS '资产创建时间';
COMMENT ON COLUMN soc_assets.updated_at IS '资产信息最后更新时间';

-- =====================================================
-- 7. 创建更新时间戳自动更新函数
-- =====================================================

CREATE OR REPLACE FUNCTION update_soc_assets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 创建触发器
DROP TRIGGER IF EXISTS trigger_update_soc_assets_updated_at ON soc_assets;
CREATE TRIGGER trigger_update_soc_assets_updated_at
    BEFORE UPDATE ON soc_assets
    FOR EACH ROW
    EXECUTE FUNCTION update_soc_assets_updated_at();

-- =====================================================
-- 8. 验证结果
-- =====================================================

DO $$
DECLARE
    column_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_name = 'soc_assets' AND table_schema = 'public';

    RAISE NOTICE '✅ soc_assets表优化完成！';
    RAISE NOTICE '   当前字段数: %', column_count;
    RAISE NOTICE '   新增字段: name, mac_address, asset_type, criticality, owner, business_unit, wazuh_agent_id, updated_at';
END $$;

COMMIT;

-- =====================================================
-- 9. 显示表结构
-- =====================================================

\d soc_assets
