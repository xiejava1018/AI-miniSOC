"""资产知识图谱 v1（G1：节点/边表 + 业务系统 + 账号→人映射 + 关系层）

详见 docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.2：
  - 新增 5 张表：soc_graph_nodes / soc_graph_edges / soc_business_systems /
                 soc_asset_business / soc_account_person
  - 改造 soc_assets：owner_id INTEGER FK（soc_users.id 为 Integer，非 UUID），
                     parent_id String → UUID FK（虚拟/容器 → 宿主机）

迁移基准（2026-09-13 实测）：
  当前 alembic 单 head ``k6l7m8n9o0p1``，无须 merge；新迁移
  down_revision 直接指向 ``k6l7m8n9o0p1``。

CLAUDE.md 反复教训复述：
  ① 用 `bind = op.get_bind(); bind.execute(sa.text(...))`，不用 `op.execute(text, params)`
     （双位置参数不兼容）
  ② JSONB 绑定用 `CAST(:v AS jsonb)`，不用 `:v::jsonb`（`::` 会被当参数）
  ③ 迁移内不写 Python 状态变量 + INSERT 后回读 SELECT
  ④ 所有引用菜单/角色行的 INSERT 必须 JOIN 来源表，禁止硬编码 id
  ⑤ FK 类型严格匹配：soc_users.id=Integer, soc_departments.id=BigInteger, soc_assets.id=UUID
"""
from alembic import op
import sqlalchemy as sa

revision = "t3u4v5w6x7y8"
down_revision = "k6l7m8n9o0p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # =========================================================================
    # ① 补丁 A：soc_assets.owner_id（INTEGER FK → soc_users.id）
    # =========================================================================
    bind.execute(sa.text(
        """
        ALTER TABLE soc_assets
            ADD COLUMN IF NOT EXISTS owner_id INTEGER
            REFERENCES soc_users(id) ON DELETE SET NULL
        """
    ))
    # 数据回填：owner 字符串 → soc_users.id（按 username 或 phone 匹配）
    bind.execute(sa.text(
        """
        UPDATE soc_assets a
        SET owner_id = u.id
        FROM soc_users u
        WHERE a.owner_id IS NULL
          AND a.owner IS NOT NULL
          AND (a.owner = u.username OR a.owner = u.phone)
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_soc_assets_owner_id
            ON soc_assets(owner_id)
            WHERE owner_id IS NOT NULL
        """
    ))
    bind.execute(sa.text(
        """
        COMMENT ON COLUMN soc_assets.owner_id IS
            'v1: 责任人外键化，优先于 owner 字符串；NULL 时 UI 回退显示 owner'
        """
    ))

    # =========================================================================
    # ② 补丁 B：soc_assets.parent_id → UUID FK（虚拟机/容器 → 宿主机）
    # =========================================================================
    # 步骤 1：清洗 — 把无效 UUID 格式 / 引用不存在的值置 NULL
    bind.execute(sa.text(
        """
        UPDATE soc_assets a
        SET parent_id = NULL
        WHERE parent_id IS NOT NULL
          AND (
              parent_id !~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
              OR NOT EXISTS (
                  SELECT 1 FROM soc_assets b WHERE b.id::text = a.parent_id
              )
          )
        """
    ))
    # 步骤 2：类型变更 + FK
    bind.execute(sa.text(
        """
        DO $$
        BEGIN
            -- 若已是 UUID 类型则跳过 ALTER TYPE
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name = 'soc_assets' AND column_name = 'parent_id') = 'text' THEN
                ALTER TABLE soc_assets
                    ALTER COLUMN parent_id TYPE UUID USING parent_id::uuid;
            END IF;
        END$$;
        """
    ))
    # FK（已存在则跳过）
    bind.execute(sa.text(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_soc_assets_parent'
                  AND table_name = 'soc_assets'
            ) THEN
                ALTER TABLE soc_assets
                    ADD CONSTRAINT fk_soc_assets_parent
                    FOREIGN KEY (parent_id) REFERENCES soc_assets(id) ON DELETE SET NULL;
            END IF;
        END$$;
        """
    ))
    bind.execute(sa.text(
        """
        COMMENT ON CONSTRAINT fk_soc_assets_parent ON soc_assets IS
            'v1: 虚拟机/容器 → 宿主机 FK'
        """
    ))

    # =========================================================================
    # ③ 业务系统实体表（补齐"资产→业务"主链的关键）
    # =========================================================================
    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_business_systems (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code         TEXT UNIQUE NOT NULL,
            name         TEXT        NOT NULL,
            criticality  TEXT        NOT NULL DEFAULT 'medium',
            owner_id     INTEGER REFERENCES soc_users(id) ON DELETE SET NULL,
            department_id BIGINT  REFERENCES soc_departments(id) ON DELETE SET NULL,
            description  TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))
    bind.execute(sa.text(
        """
        COMMENT ON TABLE soc_business_systems IS
            'v1: 业务系统实体，补齐资产 → 业务 → 部门 → 责任人的主链'
        """
    ))

    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_asset_business (
            asset_id  UUID NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
            system_id UUID NOT NULL REFERENCES soc_business_systems(id) ON DELETE CASCADE,
            role      TEXT,
            PRIMARY KEY (asset_id, system_id)
        )
        """
    ))

    # =========================================================================
    # ④ soc_account_person：账号字符串 → 自然人 user_id 映射
    # =========================================================================
    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_account_person (
            account       TEXT PRIMARY KEY,
            user_id       INTEGER REFERENCES soc_users(id) ON DELETE SET NULL,
            match_method  TEXT NOT NULL DEFAULT 'manual',
            confidence    NUMERIC(4,3) NOT NULL DEFAULT 1.000
                          CHECK (confidence >= 0 AND confidence <= 1),
            verified_at   TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_account_person_user
            ON soc_account_person(user_id) WHERE user_id IS NOT NULL
        """
    ))
    bind.execute(sa.text(
        """
        COMMENT ON TABLE soc_account_person IS
            'v1: 账号字符串 → 自然人 user_id 映射, IdentityGraphBuilder 据此产生 owned_by 边'
        """
    ))
    # 规则推断回填：登录名前缀 = username 匹配
    bind.execute(sa.text(
        """
        INSERT INTO soc_account_person (account, user_id, match_method, confidence, verified_at)
        SELECT DISTINCT ib.account, u.id, 'email', 0.85, now()
        FROM soc_identity_bindings ib
        JOIN soc_users u ON split_part(ib.account, '@', 1) = u.username
        ON CONFLICT (account) DO NOTHING
        """
    ))

    # =========================================================================
    # ⑤ 图节点表（跨实体统一寻址）
    # =========================================================================
    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_graph_nodes (
            node_key         TEXT        PRIMARY KEY,
            node_type        TEXT        NOT NULL,
            ref_table        TEXT,
            ref_id           TEXT,
            label            TEXT        NOT NULL,
            props            JSONB       NOT NULL DEFAULT '{}'::jsonb,
            props_synced_at  TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_gn_type ON soc_graph_nodes(node_type)
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_gn_ref  ON soc_graph_nodes(ref_table, ref_id)
        """
    ))

    # =========================================================================
    # ⑥ 图边表（邻接表 + 生命周期 + 置信度 + 证据）
    # =========================================================================
    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_graph_edges (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            src_key              TEXT        NOT NULL
                                  REFERENCES soc_graph_nodes(node_key) ON DELETE CASCADE,
            dst_key              TEXT        NOT NULL
                                  REFERENCES soc_graph_nodes(node_key) ON DELETE CASCADE,
            rel_type             TEXT        NOT NULL,
            direction            TEXT        NOT NULL DEFAULT 'directed',
            weight               NUMERIC(5,3) NOT NULL DEFAULT 1.000,
            confidence           NUMERIC(4,3) NOT NULL DEFAULT 1.000,
            sources              JSONB       NOT NULL DEFAULT '[]'::jsonb,
            last_seen_by_source  JSONB       NOT NULL DEFAULT '{}'::jsonb,
            evidence             JSONB       NOT NULL DEFAULT '{}'::jsonb,
            first_seen           TIMESTAMPTZ,
            last_seen            TIMESTAMPTZ,
            expires_at           TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_graph_edge UNIQUE (src_key, dst_key, rel_type),
            CONSTRAINT ck_edge_conf  CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT ck_edge_dir   CHECK (direction IN ('directed', 'undirected'))
        )
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_ge_src  ON soc_graph_edges(src_key)
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_ge_dst  ON soc_graph_edges(dst_key)
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_ge_type ON soc_graph_edges(rel_type)
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_ge_conf ON soc_graph_edges(rel_type, confidence DESC)
        """
    ))
    bind.execute(sa.text(
        """
        CREATE INDEX IF NOT EXISTS idx_ge_exp
            ON soc_graph_edges(expires_at) WHERE expires_at IS NOT NULL
        """
    ))

    # =========================================================================
    # ⑦ 网络链路表（v1 仅人工登记，采集留 v2）
    # =========================================================================
    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_network_links (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            src_key   TEXT NOT NULL,
            dst_key   TEXT NOT NULL,
            link_type TEXT NOT NULL DEFAULT 'l2',
            confidence NUMERIC(4,3) NOT NULL DEFAULT 0.500,
            source    TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))

    # =========================================================================
    # ⑧ 菜单：资产图谱（挂在资产管理 /assets 下，作为第 8 项子菜单）
    # =========================================================================
    bind.execute(sa.text(
        """
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions, created_at, updated_at)
        SELECT p.id, '资产图谱', '资产图谱', 'graph', 'ri:share-circle-line',
               '/asset/graph/index', 8, TRUE,
               '[{"title":"查看","authMark":"view"},
                 {"title":"重建边","authMark":"rebuild"},
                 {"title":"导出","authMark":"export"}]'::jsonb,
               NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/assets' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus
              WHERE path = 'graph' AND parent_id = p.id
          )
        """
    ))
    # 授权：admin/operator 全权限，viewer 只读，auditor 读+导出
    bind.execute(sa.text(
        """
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id,
               CASE r.code
                   WHEN 'admin'    THEN '["view","rebuild","export"]'::jsonb
                   WHEN 'operator' THEN '["view","rebuild","export"]'::jsonb
                   WHEN 'viewer'   THEN '["view"]'::jsonb
                   WHEN 'auditor'  THEN '["view","export"]'::jsonb
                   ELSE '["view"]'::jsonb
               END
        FROM soc_roles r
        CROSS JOIN soc_menus m
        WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor')
          AND m.path = 'graph'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm
              WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
        """
    ))


def downgrade() -> None:
    bind = op.get_bind()

    # 菜单 + 授权回退
    bind.execute(sa.text(
        """
        DELETE FROM soc_role_menus WHERE menu_id IN (
            SELECT m.id FROM soc_menus m
            JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/assets'
            WHERE m.path = 'graph'
        )
        """
    ))
    bind.execute(sa.text(
        """
        DELETE FROM soc_menus
        WHERE path = 'graph' AND parent_id IN (
            SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL
        )
        """
    ))

    # 网络链路表
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_network_links"))

    # 图边 / 节点表
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_graph_edges"))
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_graph_nodes"))

    # 账号→人
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_account_person"))

    # 业务系统 + 关联
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_asset_business"))
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_business_systems"))

    # 补丁 B：parent_id 回退为 String（先删 FK，再转类型）
    bind.execute(sa.text(
        """
        ALTER TABLE soc_assets
            DROP CONSTRAINT IF EXISTS fk_soc_assets_parent
        """
    ))
    # 若已是 uuid 类型则转回 text；保留清洗前的 NULL 行为
    bind.execute(sa.text(
        """
        DO $$
        BEGIN
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name = 'soc_assets' AND column_name = 'parent_id') = 'uuid' THEN
                ALTER TABLE soc_assets
                    ALTER COLUMN parent_id TYPE TEXT USING parent_id::text;
            END IF;
        END$$;
        """
    ))

    # 补丁 A：owner_id 回退
    bind.execute(sa.text(
        """
        DROP INDEX IF EXISTS idx_soc_assets_owner_id
        """
    ))
    bind.execute(sa.text(
        """
        ALTER TABLE soc_assets DROP COLUMN IF EXISTS owner_id
        """
    ))