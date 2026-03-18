-- ============================================================================
-- AI-miniSOC soc_asset_ports表ALTER TABLE变更脚本
-- ============================================================================
-- 功能：更新已存在的soc_asset_ports表结构
-- 版本：v1.0
-- 日期：2026-03-18
--
-- 基于现有结构：
--   id, asset_ip(TEXT), port, protocol, service, version, status, scanned_at
--
-- 变更内容：
--   1. asset_ip: TEXT → INET
--   2. 新增字段：asset_id, service_banner, vulnerability, last_seen
--   3. 新增索引
--
-- 适用场景：soc_asset_ports表已存在且有数据
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 修改asset_ip字段类型 (TEXT → INET)
-- ============================================================================

-- 先删除相关的索引和约束
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

-- ============================================================================
-- 2. 添加新字段
-- ============================================================================

-- 添加asset_id字段（用于关联soc_assets）
ALTER TABLE soc_asset_ports ADD COLUMN IF NOT EXISTS asset_id TEXT;

-- 添加service_banner字段（服务指纹）
ALTER TABLE soc_asset_ports ADD COLUMN IF NOT EXISTS service_banner TEXT;

-- 添加vulnerability字段（漏洞信息）
ALTER TABLE soc_asset_ports ADD COLUMN IF NOT EXISTS vulnerability TEXT;

-- 添加last_seen字段（最后检测时间）
ALTER TABLE soc_asset_ports ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- ============================================================================
-- 3. 创建新索引
-- ============================================================================

-- 服务名称索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_service ON soc_asset_ports(service);

-- 协议索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_protocol ON soc_asset_ports(protocol);

-- 状态索引
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_status ON soc_asset_ports(status);

-- 扫描时间索引（降序）
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_scanned_at ON soc_asset_ports(scanned_at DESC);

-- 复合索引：IP + 端口
CREATE INDEX IF NOT EXISTS idx_soc_asset_ports_ip_port ON soc_asset_ports(asset_ip, port);

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
    RAISE NOTICE '   asset_ip类型: % (期望: inet)', asset_ip_type;
    RAISE NOTICE '   索引数量: % (期望: 6)', index_count;
END $$;

-- 提交事务
COMMIT;

-- ============================================================================
-- 完成
-- ============================================================================
