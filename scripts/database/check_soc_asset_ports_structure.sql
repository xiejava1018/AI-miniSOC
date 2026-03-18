-- ============================================================================
-- 查询soc_asset_ports表当前结构
-- ============================================================================
-- 用途：在Bytebase中执行此SQL，查看表的实际结构
-- ============================================================================

SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'soc_asset_ports'
AND table_schema = 'public'
ORDER BY ordinal_position;

-- 查看现有索引
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'soc_asset_ports'
AND schemaname = 'public';

-- 查看现有约束
SELECT
    conname,
    pg_get_constraintdef(oid) as definition
FROM pg_constraint
WHERE conrelid = 'soc_asset_ports'::regclass
AND connamespace = 'public'::regnamespace;
