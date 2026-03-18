-- ============================================================================
-- AI-miniSOC soc_asset_ports表ALTER TABLE变更脚本（基于实际结构）
-- ============================================================================
-- 功能：更新soc_asset_ports表结构（MVP v0.1）
-- 版本：v1.2
-- 日期：2026-03-18
--
-- 基于实际表结构（通过psql查询确认）：
--   - 主键：id (uuid, gen_random_uuid)
--   - 外键：asset_id → soc_assets(id) ON DELETE CASCADE
--   - 字段：state (非status), scan_time (非scanned_at)
--
-- 变更内容：
--   1. asset_ip: text → INET（与soc_assets保持一致）
--   2. 新增字段：service_banner, vulnerability, last_seen
--   3. 新增索引：service, protocol, state, scan_time, (asset_ip, port)
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 修改asset_ip字段类型 (TEXT → INET)
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
        -- 删除唯一约束
        ALTER TABLE soc_asset_ports DROP CONSTRAINT IF EXISTS unique_asset_port;

        -- 删除索引
        DROP INDEX IF EXISTS idx_asset_ports_asset_ip;

        -- 修改字段类型
        ALTER TABLE soc_asset_ports
        ALTER COLUMN asset_ip TYPE INET USING asset_ip::INET;

        -- 恢复唯一约束
        ALTER TABLE soc_asset_ports
        ADD CONSTRAINT unique_asset_port
        UNIQUE (asset_ip, port, protocol);

        -- 重建索引
        CREATE INDEX idx_asset_ports_asset_ip ON soc_asset_ports(asset_ip);

        RAISE NOTICE '✅ 修改字段类型: asset_ip (TEXT → INET)';
    ELSE
        RAISE NOTICE '⊙ 字段类型已是INET或无需修改';
    END IF;
END $$;

-- ============================================================================
-- 2. 添加新字段
-- ============================================================================

-- 添加service_banner字段（服务指纹）
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
-- 3. 创建新索引（只在字段存在时创建，避免警告）
-- ============================================================================

-- service索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'service'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_service
        ON soc_asset_ports(service);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_service';
    END IF;
END $$;

-- protocol索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'protocol'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_protocol
        ON soc_asset_ports(protocol);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_protocol';
    END IF;
END $$;

-- state索引（注意：实际字段名是state，不是status）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'state'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_state
        ON soc_asset_ports(state);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_state';
    END IF;
END $$;

-- scan_time索引（降序，注意：实际字段名是scan_time，不是scanned_at）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'scan_time'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_scan_time
        ON soc_asset_ports(scan_time DESC);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_scan_time';
    END IF;
END $$;

-- 复合索引：IP + 端口
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
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_ip_port';
    END IF;
END $$;

-- ============================================================================
-- 4. 添加表和字段注释
-- ============================================================================

COMMENT ON TABLE soc_asset_ports IS '资产端口表 - 存储资产开放端口和服务信息';
COMMENT ON COLUMN soc_asset_ports.id IS '主键（UUID）';
COMMENT ON COLUMN soc_asset_ports.asset_id IS '关联资产ID（外键 → soc_assets.id）';
COMMENT ON COLUMN soc_asset_ports.asset_ip IS '关联的资产IP（INET类型，与soc_assets保持一致）';
COMMENT ON COLUMN soc_asset_ports.port IS '端口号';
COMMENT ON COLUMN soc_asset_ports.protocol IS '协议类型：tcp/udp';
COMMENT ON COLUMN soc_asset_ports.state IS '端口状态：open/closed/filtered';
COMMENT ON COLUMN soc_asset_ports.service IS '服务名称（如：ssh, http, mysql）';
COMMENT ON COLUMN soc_asset_ports.version IS '服务版本号';
COMMENT ON COLUMN soc_asset_ports.scan_time IS '扫描时间';
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
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports' AND table_schema = 'public';

    SELECT data_type INTO asset_ip_type
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports' AND column_name = 'asset_ip';

    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE tablename = 'soc_asset_ports' AND schemaname = 'public';

    RAISE NOTICE '✅ soc_asset_ports表更新完成！';
    RAISE NOTICE '   字段总数: % (期望: 12)', column_count;
    RAISE NOTICE '   asset_ip类型: % (期望: inet)', asset_ip_type;
    RAISE NOTICE '   索引数量: % (期望: 8)', index_count;
END $$;

-- 提交事务
COMMIT;

-- ============================================================================
-- 完成
-- ============================================================================
