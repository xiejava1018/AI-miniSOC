-- ============================================================================
-- AI-miniSOC 数据库初始化脚本 (Bytebase兼容版)
-- ============================================================================
-- 功能：创建soc_assets表及相关对象
-- 版本：v1.1 (Bytebase兼容)
-- 日期：2026-03-18
--
-- 变更说明：
-- - 移除DROP TRIGGER IF EXISTS（Bytebase不支持）
-- - 简化触发器创建逻辑
-- - 移除\dt和\d等psql元命令
-- ============================================================================

-- 设置搜索路径
SET search_path TO public;

-- ============================================================================
-- 1. 创建soc_assets表
-- ============================================================================

CREATE TABLE soc_assets (
    -- 主键
    id TEXT PRIMARY KEY,

    -- 网络信息
    asset_ip INET UNIQUE NOT NULL,
    mac_address MACADDR,

    -- 基本信息
    name VARCHAR(255),
    asset_description TEXT,

    -- 分类信息
    asset_type VARCHAR(50) DEFAULT 'other',
    criticality VARCHAR(20) DEFAULT 'medium',
    owner VARCHAR(255),
    business_unit VARCHAR(255),

    -- 状态信息
    asset_status VARCHAR(20) DEFAULT '离线',
    wazuh_agent_id VARCHAR(100) UNIQUE,

    -- 时间戳
    status_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 约束
    CONSTRAINT soc_assets_asset_type_check
        CHECK (asset_type IN (
            'server',       -- 服务器
            'workstation',  -- 工作站
            'printer',      -- 打印机
            'router',       -- 路由器
            'switch',       -- 交换机
            'nas',          -- 网络存储
            'firewall',     -- 防火墙
            'other'         -- 其他
        )),

    CONSTRAINT soc_assets_criticality_check
        CHECK (criticality IN (
            'critical',  -- 关键资产
            'high',      -- 重要资产
            'medium',    -- 一般资产
            'low'        -- 低优先级
        ))
);

-- ============================================================================
-- 2. 创建soc_asset_ports表
-- ============================================================================

CREATE TABLE soc_asset_ports (
    id SERIAL PRIMARY KEY,
    asset_ip INET NOT NULL,
    port INTEGER NOT NULL,
    protocol TEXT DEFAULT 'tcp',
    service TEXT,
    version TEXT,
    status TEXT DEFAULT 'open',
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(asset_ip, port, protocol)
);

-- ============================================================================
-- 3. 创建索引
-- ============================================================================

-- soc_assets索引
CREATE INDEX idx_soc_assets_ip ON soc_assets(asset_ip);
CREATE INDEX idx_soc_assets_wazuh ON soc_assets(wazuh_agent_id);
CREATE INDEX idx_soc_assets_type ON soc_assets(asset_type);
CREATE INDEX idx_soc_assets_criticality ON soc_assets(criticality);
CREATE INDEX idx_soc_assets_status ON soc_assets(asset_status);

-- soc_asset_ports索引
CREATE INDEX idx_soc_asset_ports_ip ON soc_asset_ports(asset_ip);
CREATE INDEX idx_soc_asset_ports_port ON soc_asset_ports(port);

-- ============================================================================
-- 4. 创建触发器函数 - 自动更新updated_at
-- ============================================================================

CREATE FUNCTION update_soc_assets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 5. 创建触发器
-- ============================================================================

CREATE TRIGGER trigger_update_soc_assets_updated_at
    BEFORE UPDATE ON soc_assets
    FOR EACH ROW
    EXECUTE FUNCTION update_soc_assets_updated_at();

-- ============================================================================
-- 6. 添加表和字段注释
-- ============================================================================

-- soc_assets表注释
COMMENT ON TABLE soc_assets IS '安全资产表 - AI-miniSOC核心资产表，整合网络扫描和手动管理功能';

COMMENT ON COLUMN soc_assets.id IS '资产唯一标识（UUID格式）';
COMMENT ON COLUMN soc_assets.asset_ip IS '资产IP地址（PostgreSQL INET类型）';
COMMENT ON COLUMN soc_assets.mac_address IS 'MAC地址（用于设备识别）';
COMMENT ON COLUMN soc_assets.name IS '资产名称';
COMMENT ON COLUMN soc_assets.asset_description IS '资产描述（详细信息）';
COMMENT ON COLUMN soc_assets.asset_type IS '资产类型：server/workstation/printer/router/switch/nas/firewall/other';
COMMENT ON COLUMN soc_assets.criticality IS '重要性等级：critical/high/medium/low';
COMMENT ON COLUMN soc_assets.owner IS '资产负责人';
COMMENT ON COLUMN soc_assets.business_unit IS '所属业务单元/部门';
COMMENT ON COLUMN soc_assets.asset_status IS '在线状态：新发现/在线/离线/已删除';
COMMENT ON COLUMN soc_assets.wazuh_agent_id IS '关联的Wazuh Agent ID（用于告警关联）';
COMMENT ON COLUMN soc_assets.status_updated_at IS '状态最后更新时间';
COMMENT ON COLUMN soc_assets.created_at IS '资产创建时间';
COMMENT ON COLUMN soc_assets.updated_at IS '资产信息最后更新时间';

-- soc_asset_ports表注释
COMMENT ON TABLE soc_asset_ports IS '资产端口表 - 存储资产开放端口和服务信息';
COMMENT ON COLUMN soc_asset_ports.asset_ip IS '关联的资产IP';
COMMENT ON COLUMN soc_asset_ports.port IS '端口号';
COMMENT ON COLUMN soc_asset_ports.protocol IS '协议类型（tcp/udp）';
COMMENT ON COLUMN soc_asset_ports.service IS '服务名称';
COMMENT ON COLUMN soc_asset_ports.version IS '服务版本';
COMMENT ON COLUMN soc_asset_ports.scanned_at IS '扫描时间';

-- ============================================================================
-- 完成
-- ============================================================================

-- 插入示例数据（可选，取消注释以启用）
/*
INSERT INTO soc_assets (id, asset_ip, name, asset_description, asset_type, criticality, asset_status) VALUES
    ('550e8400-e29b-41d4-a716-446655440001', '192.168.0.40', 'Wazuh服务器', 'Wazuh SIEM服务器', 'server', 'critical', '在线'),
    ('550e8400-e29b-41d4-a716-446655440002', '192.168.0.30', 'Grafana服务器', '监控可视化服务器', 'server', 'high', '在线')
ON CONFLICT (asset_ip) DO NOTHING;
*/
