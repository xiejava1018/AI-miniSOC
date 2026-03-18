-- ============================================================================
-- AI-miniSOC soc_asset_ports表更新脚本 (Bytebase兼容版)
-- ============================================================================
-- 功能：更新soc_asset_ports表结构
-- 版本：v1.0
-- 日期：2026-03-18
--
-- 主要变更：
-- 1. asset_ip从TEXT改为INET类型（与soc_assets保持一致）
-- 2. 添加实用字段
-- 3. 创建优化索引
--
-- 适用场景：soc_asset_ports表已存在，需要更新结构
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 修改asset_ip字段类型（TEXT → INET）
-- ============================================================================

DO $$
BEGIN
    -- 检查当前字段类型
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports'
        AND column_name = 'asset_ip'
        AND data_type = 'text'
    ) THEN
        -- 临时删除唯一约束（如果存在）
        ALTER TABLE soc_asset_ports DROP CONSTRAINT IF EXISTS soc_asset_ports_asset_ip_port_key;

        -- 删除索引（如果存在）
        DROP INDEX IF EXISTS idx_soc_asset_ports_ip;

        -- 修改字段类型
        ALTER TABLE soc_asset_ports
        ALTER COLUMN asset_ip TYPE INET USING asset_ip::INET;

        -- 恢复唯一约束
        ALTER TABLE soc_asset_ports
        ADD CONSTRAINT soc_asset_ports_asset_ip_port_key
        UNIQUE (asset_ip, port, protocol);

        RAISE NOTICE '✅ 修改字段类型: asset_ip (TEXT → INET)';
    ELSE
        RAISE NOTICE '⊙ 字段类型已是INET或无需修改';
    END IF;
END $$;

-- ============================================================================
-- 2. 添加新字段（可选，按需启用）
-- ============================================================================

-- 添加asset_id字段（关联soc_assets，用于查询优化）
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

-- 添加service_banner字段（服务指纹信息）
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

-- 添加vulnerability字段（漏洞信息）
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

-- 添加last_seen字段（最后检测时间）
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
-- 3. 创建索引（只在字段存在时）
-- ============================================================================

-- 服务名称索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'service'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_service
        ON soc_asset_ports(service);
    END IF;
END $$;

-- 协议索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'protocol'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_protocol
        ON soc_asset_ports(protocol);
    END IF;
END $$;

-- 状态索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_status
        ON soc_asset_ports(status);
    END IF;
END $$;

-- 扫描时间索引（降序）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'scanned_at'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_scanned_at
        ON soc_asset_ports(scanned_at DESC);
    END IF;
END $$;

-- 复合索引：IP + 端口（常用查询优化）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'asset_ip'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'port'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_ip_port
        ON soc_asset_ports(asset_ip, port);
    END IF;
END $$;

-- ============================================================================
-- 4. 添加表和字段注释
-- ============================================================================

COMMENT ON TABLE soc_asset_ports IS '资产端口表 - 存储资产开放端口和服务信息';
COMMENT ON COLUMN soc_asset_ports.asset_ip IS '关联的资产IP（INET类型，与soc_assets保持一致）';
COMMENT ON COLUMN soc_asset_ports.port IS '端口号';
COMMENT ON COLUMN soc_asset_ports.protocol IS '协议类型：tcp/udp';
COMMENT ON COLUMN soc_asset_ports.service IS '服务名称（如：ssh, http, mysql）';
COMMENT ON COLUMN soc_asset_ports.version IS '服务版本号';
COMMENT ON COLUMN soc_asset_ports.status IS '端口状态：open/closed/filtered';
COMMENT ON COLUMN soc_asset_ports.scanned_at IS '扫描时间';
COMMENT ON COLUMN soc_asset_ports.asset_id IS '关联资产ID（冗余字段，用于优化查询性能）';
COMMENT ON COLUMN soc_asset_ports.service_banner IS '服务指纹/特征信息（用于服务识别）';
COMMENT ON COLUMN soc_asset_ports.vulnerability IS '已知CVE漏洞信息（逗号分隔）';
COMMENT ON COLUMN soc_asset_ports.last_seen IS '最后检测到该端口开放的时间';

-- ============================================================================
-- 5. 验证结果
-- ============================================================================

DO $$
DECLARE
    column_count INTEGER;
    asset_ip_type TEXT;
    index_count INTEGER;
BEGIN
    -- 统计字段数
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports' AND table_schema = 'public';

    -- 检查asset_ip类型
    SELECT data_type INTO asset_ip_type
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports' AND column_name = 'asset_ip';

    -- 统计索引数
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE tablename = 'soc_asset_ports';

    RAISE NOTICE '✅ soc_asset_ports表更新完成！';
    RAISE NOTICE '   字段总数: %', column_count;
    RAISE NOTICE '   asset_ip类型: % (应该是: inet)', asset_ip_type;
    RAISE NOTICE '   索引数量: %', index_count;
END $$;

-- 提交事务
COMMIT;

-- ============================================================================
-- 完成
-- ============================================================================
