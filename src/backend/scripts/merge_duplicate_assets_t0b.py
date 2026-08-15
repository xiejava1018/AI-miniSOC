"""T0b 重复资产合并脚本（一次性运维操作）

策略（方案 §1.5）：
- 同 IP 双记录中，保留优先级更高的一方：wazuh（有 agent）> tplink-router > manual
- 被合并方（manual 侧）的端口/标签/来源/事件关联/漏洞关联先迁移到保留方（避免数据丢失）
- 冲突端口（保留方已有同端口同协议）不迁移，随被合并方删除
- 被合并方最后删除（物理删除，因同 IP 双记录无保留价值且保留方已承接全部信息）
"""
from app.core.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

dup_groups = db.execute(text("""
    SELECT asset_ip FROM soc_assets GROUP BY asset_ip HAVING count(*) > 1
""")).fetchall()
print(f"发现 {len(dup_groups)} 组同 IP 重复资产")

# 优先级：有 agent 的 wazuh > 有名字的 tplink > 无名 tplink > manual
PRIORITY = """
    CASE
        WHEN data_source = 'wazuh' AND wazuh_agent_id IS NOT NULL THEN 0
        WHEN data_source = 'wazuh' THEN 1
        WHEN data_source = 'tplink-router' AND name IS NOT NULL AND name NOT IN ('', '---') THEN 2
        WHEN data_source = 'tplink-router' THEN 3
        ELSE 4
    END
"""

merged, migrated_ports, conflict_ports = 0, 0, 0
for (ip,) in dup_groups:
    rows = db.execute(text(f"""
        SELECT id, name, data_source, wazuh_agent_id, {PRIORITY} AS prio
        FROM soc_assets WHERE asset_ip = :ip ORDER BY prio, created_at
    """), {"ip": ip}).fetchall()
    keep = rows[0]
    for drop in rows[1:]:
        # 1. 迁移端口（跳过保留方已有的同 port+protocol 冲突）
        ports = db.execute(text(
            "SELECT id, port, protocol FROM soc_asset_ports WHERE asset_id = :d"
        ), {"d": drop.id}).fetchall()
        for p in ports:
            exists = db.execute(text(
                "SELECT 1 FROM soc_asset_ports WHERE asset_id = :k AND port = :p AND protocol = :pr"
            ), {"k": keep.id, "p": p.port, "pr": p.protocol}).fetchone()
            if exists:
                conflict_ports += 1
            else:
                db.execute(text(
                    "UPDATE soc_asset_ports SET asset_id = :k WHERE id = :pid"
                ), {"k": keep.id, "pid": p.id})
                migrated_ports += 1
        # 2. 迁移标签/来源/事件关联（全量迁移，均无唯一约束冲突风险小；标签有唯一键则跳过冲突）
        db.execute(text(
            "UPDATE soc_asset_tags SET asset_id = :k WHERE asset_id = :d AND NOT EXISTS "
            "(SELECT 1 FROM soc_asset_tags t2 WHERE t2.asset_id = :k AND t2.tag_key = soc_asset_tags.tag_key)"
        ), {"k": keep.id, "d": drop.id})
        db.execute(text(
            "UPDATE soc_asset_sources SET asset_id = :k WHERE asset_id = :d AND NOT EXISTS "
            "(SELECT 1 FROM soc_asset_sources s2 WHERE s2.asset_id = :k AND s2.source = soc_asset_sources.source AND s2.source_id = soc_asset_sources.source_id)"
        ), {"k": keep.id, "d": drop.id})
        db.execute(text(
            "UPDATE soc_asset_incidents SET asset_id = :k WHERE asset_id = :d AND NOT EXISTS "
            "(SELECT 1 FROM soc_asset_incidents i2 WHERE i2.asset_id = :k AND i2.incident_id = soc_asset_incidents.incident_id)"
        ), {"k": keep.id, "d": drop.id})
        db.execute(text(
            "UPDATE soc_asset_vulnerabilities SET asset_id = :k WHERE asset_id = :d AND NOT EXISTS "
            "(SELECT 1 FROM soc_asset_vulnerabilities v2 WHERE v2.asset_id = :k AND v2.vulnerability_id = soc_asset_vulnerabilities.vulnerability_id AND v2.scanner = soc_asset_vulnerabilities.scanner)"
        ), {"k": keep.id, "d": drop.id})
        # 其余引用 soc_assets 的外键表（alert_groups/alert_group_analyses/change_logs/sca_checks）：
        # 同样迁移到保留方（无唯一约束，直接 UPDATE）
        for tbl, col in (
            ("soc_alert_groups", "linked_asset_id"),
            ("soc_alert_group_analyses", "linked_asset_id"),
            ("soc_asset_change_logs", "asset_id"),
            ("soc_asset_sca_checks", "asset_id"),
        ):
            db.execute(text(
                f"UPDATE {tbl} SET {col} = :k WHERE {col} = :d"
            ), {"k": keep.id, "d": drop.id})
        # 3. 保留方信息补全：名称/类型等空字段从被合并方补（保留方优先，不覆盖）
        db.execute(text("""
            UPDATE soc_assets SET
                name = COALESCE(NULLIF(name, NULL), (SELECT name FROM soc_assets WHERE id = :d)),
                asset_description = COALESCE(asset_description, (SELECT asset_description FROM soc_assets WHERE id = :d))
            WHERE id = :k
        """), {"d": drop.id, "k": keep.id})
        # 4. 删除被合并方（从属数据已迁移或为冲突端口，cascade 清理）
        db.execute(text("DELETE FROM soc_assets WHERE id = :d"), {"d": drop.id})
        merged += 1
        print(f"  [{ip}] 保留 {str(keep.id)[:8]}({keep.data_source}/{keep.name or '?'}) "
              f"<- 删除 {str(drop.id)[:8]}({drop.data_source}/{drop.name or '?'})")

db.commit()

# 验收
left = db.execute(text(
    "SELECT asset_ip, count(*) FROM soc_assets GROUP BY asset_ip HAVING count(*) > 1"
)).fetchall()
total = db.execute(text("SELECT count(*) FROM soc_assets")).scalar()
print(f"\n合并 {merged} 条 | 迁移端口 {migrated_ports} 个（冲突跳过 {conflict_ports} 个）")
print(f"验收：资产总数 {total}，剩余同 IP 重复组 {len(left)}")
db.close()
