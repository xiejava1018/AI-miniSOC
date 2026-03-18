-- ============================================================================
-- AI-miniSOC soc_asset_ports表更新脚本
-- ============================================================================
-- 功能：更新soc_asset_ports表结构
-- 版本：v1.0
-- 日期：2026-03-18
--
-- 主要变更：
-- 1. asset_ip从TEXT改为INET类型（与soc_assets保持一致）
-- 2. 添加外键约束（可选，关联到soc_assets）
-- 3. 添加更多索引以优化查询
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 检查并修改字段类型
-- ============================================================================

-- 修改asset_ip字段类型从TEXT到INET
DO $$
BEGIN
    -- 检查当前字段类型
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports'
        AND column_name = 'asset_ip'
        AND data_type = 'text'
    ) THEN
        -- 需要先删除依赖（索引、唯一约束）
        DROP INDEX IF EXISTS idx_soc_asset_ports_ip;
        ALTER TABLE soc_asset_ports DROP CONSTRAINT IF EXISTS soc_asset_ports_asset_ip_port_key;

        -- 修改字段类型
        ALTER TABLE soc_asset_ports
        ALTER COLUMN asset_ip TYPE INET USING asset_ip::INET;

        -- 恢复唯一约束
        ALTER TABLE soc_asset_ports
        ADD CONSTRAINT soc_asset_ports_asset_ip_port_key
        UNIQUE (asset_ip, port, protocol);

        -- 恢复索引
        CREATE INDEX idx_soc_asset_ports_ip ON soc_asset_ports(asset_ip);

        RAISE NOTICE '✅ 修改字段类型: asset_ip (TEXT → INET)';
    ELSE
        RAISE NOTICE '⊙ 字段类型已是INET或表不存在';
    END IF;
END $$;

-- ============================================================================
-- 2. 添加新字段（如果需要）
-- ============================================================================

-- 添加asset_id字段（关联soc_assets.id，替代asset_ip外键）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'asset_id'
    ) THEN
        ALTER TABLE soc_asset_ports ADD COLUMN asset_id TEXT;
        RAISE NOTICE '✅ 添加字段: asset_id';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: asset_id';
    END IF;
END $$;

-- 添加service_banner字段（服务指纹/特征）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'service_banner'
    ) THEN
        ALTER TABLE soc_asset_ports ADD COLUMN service_banner TEXT;
        RAISE NOTICE '✅ 添加字段: service_banner';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: service_banner';
    END IF;
END $$;

-- 添加vulnerability字段（已知漏洞）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'vulnerability'
    ) THEN
        ALTER TABLE soc_asset_ports ADD COLUMN vulnerability TEXT;
        RAISE NOTICE '✅ 添加字段: vulnerability';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: vulnerability';
    END IF;
END $$;

-- 添加last_seen字段（最后检测到的时间）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'last_seen'
    ) THEN
        ALTER TABLE soc_asset_ports ADD COLUMN last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        RAISE NOTICE '✅ 添加字段: last_seen';
    ELSE
        RAISE NOTICE '⊙ 字段已存在: last_seen';
    END IF;
END $$;

-- ============================================================================
-- 3. 创建/更新索引
-- ============================================================================

-- 服务名称索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_service ON soc_asset_ports(service);

-- 协议索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_protocol ON soc_asset_ports(protocol);

-- 状态索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_status ON soc_asset_ports(status);

-- 扫描时间索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_scanned_at ON soc_asset_ports(scanned_at DESC);

-- 复合索引：IP + 端口（常用查询）
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_ip_port ON soc_asset_ports(asset_ip, port);

-- ============================================================================
-- 4. 添加注释
-- ============================================================================

COMMENT ON TABLE soc_asset_ports IS '资产端口表 - 存储资产开放端口和服务信息';
COMMENT ON COLUMN soc_asset_ports.asset_ip IS '关联的资产IP（INET类型）';
COMMENT ON COLUMN soc_asset_ports.port IS '端口号';
COMMENT ON COLUMN soc_asset_ports.protocol IS '协议类型：tcp/udp';
COMMENT ON COLUMN soc_asset_ports.service IS '服务名称（如：ssh, http, mysql）';
COMMENT ON COLUMN soc_asset_ports.version IS '服务版本号';
COMMENT ON COLUMN soc_asset_ports.status IS '端口状态：open/closed/filtered';
COMMENT ON COLUMN soc_asset_ports.scanned_at IS '扫描时间';
COMMENT ON COLUMN soc_asset_ports.asset_id IS '关联资产ID（冗余字段，用于优化查询）';
COMMENT ON COLUMN soc_asset_ports.service_banner IS '服务特征/指纹信息';
COMMENT ON COLUMN soc_asset_ports.vulnerability IS '已知CVE漏洞信息';
COMMENT ON COLUMN soc_asset_ports.last_seen IS '最后检测到该端口开放的时间';

-- ============================================================================
-- 5. 验证结果
-- ============================================================================

DO $$
DECLARE
    column_count INTEGER;
    asset_ip_type TEXT;
BEGIN
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports' AND table_schema = 'public';

    SELECT data_type INTO asset_ip_type
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports' AND column_name = 'asset_ip';

    RAISE NOTICE '✅ soc_asset_ports表更新完成！';
    RAISE NOTICE '   表字段数: %', column_count;
    RAISE NOTICE '   asset_ip类型: %', asset_ip_type;
    RAISE NOTICE '   应该是: inet';
END $$;

-- 提交事务
COMMIT;
