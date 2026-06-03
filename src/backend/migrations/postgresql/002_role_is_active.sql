-- 002_role_is_active.sql
-- 给 soc_roles 表补 is_active 字段
-- 历史: ORM model 早声明了 is_active (Pydantic schema 一直用它做入参/出参),
--       但 DB 实际表没有这一列,导致 /roles/{id} PUT 时 ORM 写不进去,
--       /roles 列表返回时 Pydantic 强行补默认值 True 掩盖了真相.
-- 修复: 添加 is_active 列,默认 TRUE (与 Pydantic default=True 对齐)
-- 幂等: IF NOT EXISTS 可重复执行

ALTER TABLE soc_roles
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- 给已存在的系统角色回填 (实际新列 DEFAULT 已自动填充,这里只是显式声明)
UPDATE soc_roles SET is_active = TRUE WHERE is_active IS NULL;
