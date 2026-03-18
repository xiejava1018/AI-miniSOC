-- ============================================================================
-- AI-miniSOC soc_asset_ports表ALTER TABLE变更脚本（修复版）
-- ============================================================================
-- 功能：更新已存在的soc_asset_ports表结构
-- 版本：v1.1
-- 日期：2026-03-18
--
-- 修复：避免"Column does not exist"警告
--  - 在创建索引前检查字段是否存在
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
        -- 删除依赖
        DROP INDEX IF EXISTS idx_soc_asset_ports_ip;
        ALTER TABLE soc_asset_ports DROP CONSTRAINT IF EXISTS soc_asset_ports_asset_ip_port_key;

        -- 修改字段类型
        ALTER TABLE soc_asset_ports
        ALTER COLUMN asset_ip TYPE INET USING asset_ip::INET;

        -- 恢复唯一约束
        ALTER TABLE soc_asset_ports
        ADD CONSTRAINT soc_asset_ports_asset_ip_port_key
        UNIQUE (asset_ip, port, protocol);

        -- 重建索引
        CREATE INDEX idx_soc_asset_ports_ip ON soc_asset_ports(asset_ip);

        RAISE NOTICE '✅ 修改字段类型: asset_ip (TEXT → INET)';
    ELSE
        RAISE NOTICE '⊙ 字段类型已是INET';
    END IF;
END $$;

-- ============================================================================
-- 2. 添加新字段
-- ============================================================================

-- 添加asset_id字段
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

-- 添加service_banner字段
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

-- 添加vulnerability字段
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

-- 添加last_seen字段
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
-- 3. 创建索引（只在字段存在时创建，避免警告）
-- ============================================================================

-- IP索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'asset_ip'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_ip
        ON soc_asset_ports(asset_ip);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_ip';
    END IF;
END $$;

-- port索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'port'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_port
        ON soc_asset_ports(port);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_port';
    END IF;
END $$;

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

-- 状态索引（如果有status字段）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'status'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_status
        ON soc_asset_ports(status);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_status';
    END IF;
END $$;

-- 扫描时间索引
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'soc_asset_ports' AND column_name = 'scanned_at'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_scanned_at
        ON soc_asset_ports(scanned_at DESC);
        RAISE NOTICE '✅ 创建索引: idx_soc_asset_ports_scanned_at';
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
COMMENT ON COLUMN soc_asset_ports.asset_ip IS '关联的资产IP（INET类型）';
COMMENT ON COLUMN soc_asset_ports.port IS '端口号';
COMMENT ON COLUMN soc_asset_ports.protocol IS '协议类型：tcp/udp';
COMMENT ON COLUMN soc_asset_ports.service IS '服务名称';
COMMENT ON COLUMN soc_asset_ports.version IS '服务版本号';
COMMENT ON COLUMN soc_asset_ports.scanned_at IS '扫描时间';
COMMENT ON COLUMN soc_asset_ports.asset_id IS '关联资产ID';
COMMENT ON COLUMN soc_asset_ports.service_banner IS '服务指纹信息';
COMMENT ON COLUMN soc_asset_ports.vulnerability IS '已知漏洞信息';
COMMENT ON COLUMN soc_asset_ports.last_seen IS '最后检测时间';

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
    RAISE NOTICE '   字段总数: %', column_count;
    RAISE NOTICE '   asset_ip类型: %', asset_ip_type;
    RAISE NOTICE '   索引数量: %', index_count;
END $$;

-- 提交事务
COMMIT;
