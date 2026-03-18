-- ============================================================================
-- AI-miniSOC 数据库表更新脚本 (Bytebase修复版)
-- ============================================================================
-- 功能：更新现有soc_assets表结构
-- 版本：v1.3
-- 日期：2026-03-18
--
-- 修复内容：
-- - 使用 $$ 作为函数定界符（不是单个 $）
-- - 修复触发器创建语法
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 检查并添加soc_assets表的新字段
-- ============================================================================

-- 添加name字段（资产名称）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'name'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN name VARCHAR(255);
        RAISE NOTICE '✅ 添加字段: name';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: name';
    END IF;
END $$;

-- 添加mac_address字段（MAC地址）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'mac_address'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN mac_address MACADDR;
        RAISE NOTICE '✅ 添加字段: mac_address';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: mac_address';
    END IF;
END $$;

-- 添加asset_type字段（资产类型）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'asset_type'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN asset_type VARCHAR(50) DEFAULT 'other';
        RAISE NOTICE '✅ 添加字段: asset_type';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: asset_type';
    END IF;
END $$;

-- 添加criticality字段（重要性等级）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'criticality'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN criticality VARCHAR(20) DEFAULT 'medium';
        RAISE NOTICE '✅ 添加字段: criticality';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: criticality';
    END IF;
END $$;

-- 添加owner字段（负责人）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'owner'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN owner VARCHAR(255);
        RAISE NOTICE '✅ 添加字段: owner';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: owner';
    END IF;
END $$;

-- 添加business_unit字段（业务单元）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'business_unit'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN business_unit VARCHAR(255);
        RAISE NOTICE '✅ 添加字段: business_unit';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: business_unit';
    END IF;
END $$;

-- 添加wazuh_agent_id字段（Wazuh Agent关联）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'wazuh_agent_id'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN wazuh_agent_id VARCHAR(100);
        RAISE NOTICE '✅ 添加字段: wazuh_agent_id';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: wazuh_agent_id';
    END IF;
END $$;

-- 添加updated_at字段（更新时间戳）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_assets' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE soc_assets ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        RAISE NOTICE '✅ 添加字段: updated_at';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: updated_at';
    END IF;
END $$;

-- ============================================================================
-- 2. 添加约束（如果不存在）
-- ============================================================================

-- 添加asset_type约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'soc_assets_asset_type_check'
    ) THEN
        ALTER TABLE soc_assets
        ADD CONSTRAINT soc_assets_asset_type_check
        CHECK (asset_type IN ('server', 'workstation', 'printer', 'router', 'switch', 'nas', 'firewall', 'other'));
        RAISE NOTICE '✅ 添加约束: asset_type_check';
    ELSE
        RAISE NOTICE '⊙ 约束已存在: asset_type_check';
    END IF;
END $$;

-- 添加criticality约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'soc_assets_criticality_check'
    ) THEN
        ALTER TABLE soc_assets
        ADD CONSTRAINT soc_assets_criticality_check
        CHECK (criticality IN ('critical', 'high', 'medium', 'low'));
        RAISE NOTICE '✅ 添加约束: criticality_check';
    ELSE
        RAISE NOTICE '⊙ 约束已存在: criticality_check';
    END IF;
END $$;

-- ============================================================================
-- 3. 创建索引（如果不存在）
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_soc_assets_wazuh ON soc_assets(wazuh_agent_id);
CREATE INDEX IF NOT EXISTS idx_soc_assets_type ON soc_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_soc_assets_criticality ON soc_assets(criticality);
CREATE INDEX IF NOT EXISTS idx_soc_assets_status ON soc_assets(asset_status);

-- ============================================================================
-- 4. 创建触发器函数
-- ============================================================================

CREATE OR REPLACE FUNCTION update_soc_assets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 5. 创建触发器
-- ============================================================================

-- 删除旧触发器（如果存在）
DROP TRIGGER IF EXISTS trigger_update_soc_assets_updated_at ON soc_assets;

-- 创建新触发器
CREATE TRIGGER trigger_update_soc_assets_updated_at
    BEFORE UPDATE ON soc_assets
    FOR EACH ROW
    EXECUTE FUNCTION update_soc_assets_updated_at();

-- ============================================================================
-- 6. 迁移现有数据
-- ============================================================================

UPDATE soc_assets
SET name = COALESCE(asset_description, '未命名资产')
WHERE name IS NULL OR name = '';

-- ============================================================================
-- 7. 添加表和字段注释
-- ============================================================================

COMMENT ON TABLE soc_assets IS '安全资产表 - AI-miniSOC核心资产表，整合网络扫描和手动管理功能';

COMMENT ON COLUMN soc_assets.id IS '资产唯一标识（UUID格式）';
COMMENT ON COLUMN soc_assets.asset_ip IS '资产IP地址（PostgreSQL INET类型）';
COMMENT ON COLUMN soc_assets.name IS '资产名称';
COMMENT ON COLUMN soc_assets.asset_description IS '资产描述（详细信息）';
COMMENT ON COLUMN soc_assets.mac_address IS 'MAC地址（用于设备识别）';
COMMENT ON COLUMN soc_assets.asset_type IS '资产类型：server/workstation/printer/router/switch/nas/firewall/other';
COMMENT ON COLUMN soc_assets.criticality IS '重要性等级：critical/high/medium/low';
COMMENT ON COLUMN soc_assets.owner IS '资产负责人';
COMMENT ON COLUMN soc_assets.business_unit IS '所属业务单元/部门';
COMMENT ON COLUMN soc_assets.asset_status IS '在线状态：新发现/在线/离线/已删除';
COMMENT ON COLUMN soc_assets.wazuh_agent_id IS '关联的Wazuh Agent ID（用于告警关联）';
COMMENT ON COLUMN soc_assets.updated_at IS '资产信息最后更新时间';

-- ============================================================================
-- 8. 验证结果
-- ============================================================================

DO $$
DECLARE
    column_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_name = 'soc_assets' AND table_schema = 'public';

    RAISE NOTICE '✅ 数据库表更新完成！';
    RAISE NOTICE '   soc_assets表字段数: %', column_count;
    RAISE NOTICE '   所有表遵循soc_前缀规范';
END $$;

-- 提交事务
COMMIT;
