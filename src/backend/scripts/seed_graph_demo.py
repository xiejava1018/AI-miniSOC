"""资产知识图谱 - 演示数据 fixtures 脚本

§8.3 测试计划 fixtures：构造"看起来真实"的演示数据（沿用真实资产名 + 虚拟 login 流），
供本地开发与演示。

用法：
    cd src/backend && PYTHONPATH=. python3 scripts/seed_graph_demo.py [--reset]

选项：
    --reset      清空图谱相关表后重建（默认不清空）
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models import (
    AccountPerson,
    Asset,
    AssetBusiness,
    AssetPort,
    AssetTag,
    AssetVulnerability,
    BusinessSystem,
    GraphEdge,
    GraphNode,
    IdentityBinding,
    IdentityEvent,
    Vulnerability,
)
from app.services.graph.builders import (
    AssetPortVulnBuilder,
    IdentityGraphBuilder,
    ManualRelationBuilder,
    TopologyBuilder,
    run_all_builders,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                   format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ---------------------------------------------------------------------------
# 演示数据 fixtures（与项目真实资产命名风格一致：srv-soc-01 等）
# ---------------------------------------------------------------------------

DEMO_NETWORK = "192.168.10.0/24"
DEMO_SEGMENT = "3F"

DEMO_ASSETS = [
    # (ip, name, type, criticality, owner_username)
    ("192.168.10.10", "srv-soc-01", "server", "critical", "zhang"),
    ("192.168.10.11", "srv-wazuh-01", "server", "critical", "zhang"),
    ("192.168.10.12", "ad-dc-01", "server", "critical", "li"),
    ("192.168.10.13", "db-core-01", "server", "critical", "wang"),
    ("192.168.10.20", "app-gateway-01", "server", "high", "li"),
    ("192.168.10.21", "app-business-01", "server", "high", "wang"),
    ("192.168.10.30", "workstation-zhang-01", "workstation", "medium", "zhang"),
    ("192.168.10.31", "workstation-li-01", "workstation", "medium", "li"),
    ("192.168.10.32", "workstation-wang-01", "workstation", "medium", "wang"),
    ("192.168.10.40", "printer-floor3-01", "iot", "low", None),
]

DEMO_PORTS = {
    "srv-soc-01": [(22, "tcp", "ssh"), (443, "tcp", "https"), (8080, "tcp", "http-alt")],
    "srv-wazuh-01": [(22, "tcp", "ssh"), (1514, "tcp", "syslog"), (55000, "tcp", "wazuh")],
    "ad-dc-01": [(389, "tcp", "ldap"), (636, "tcp", "ldaps"), (445, "tcp", "smb")],
    "db-core-01": [(3306, "tcp", "mysql"), (5432, "tcp", "postgres")],
    "app-gateway-01": [(80, "tcp", "http"), (443, "tcp", "https")],
    "app-business-01": [(8080, "tcp", "http")],
}

DEMO_VULNS = [
    # (cve_id, title, cvss, severity)
    ("CVE-2023-44487", "HTTP/2 Rapid Reset", 7.5, "high"),
    ("CVE-2024-3094", "XZ Utils Backdoor", 10.0, "critical"),
    ("CVE-2023-36884", "Office Search Path", 8.8, "high"),
    ("CVE-2024-21412", "Windows Mark-of-the-Web Bypass", 8.1, "high"),
    ("CVE-2022-30190", "Follina MSDT", 7.8, "high"),
]

DEMO_BUSINESS_SYSTEMS = [
    # (code, name, criticality)
    ("soc-platform", "SOC 安全平台", "critical"),
    ("core-biz", "核心业务系统", "critical"),
    ("identity-mgmt", "统一身份认证", "high"),
]

DEMO_TAGS = {
    # asset_name → [(key, value)]
    "srv-soc-01": [("env", "prod"), ("tier", "tier-1")],
    "srv-wazuh-01": [("env", "prod"), ("tier", "tier-1")],
    "ad-dc-01": [("env", "prod"), ("tier", "tier-1")],
    "db-core-01": [("env", "prod"), ("tier", "tier-1")],
    "app-gateway-01": [("env", "prod"), ("tier", "tier-2")],
    "app-business-01": [("env", "prod"), ("tier", "tier-2")],
    "workstation-zhang-01": [("env", "prod"), ("dept", "security")],
    "workstation-li-01": [("env", "prod"), ("dept", "ops")],
    "workstation-wang-01": [("env", "prod"), ("dept", "dev")],
}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _ensure_user(db, username: str):
    """确保演示账号对应的 soc_users 记录存在。"""
    from app.models import User, Department, Role
    role = db.query(Role).filter(Role.code == "admin").first()
    if not role:
        role = Role(code="admin", name="Admin")
        db.add(role)
        db.flush()
    dept = db.query(Department).filter(Department.name == "演示组").first()
    if not dept:
        dept = Department(name="演示组")
        db.add(dept)
        db.flush()
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            password_hash="x" * 60,
            full_name=f"演示-{username}",
            role_id=role.id,
            department_id=dept.id,
        )
        db.add(user)
        db.flush()
    return user


def _seed_assets(db) -> dict[str, Asset]:
    """种入演示资产，返回 ip → Asset 映射。"""
    assets: dict[str, Asset] = {}
    for ip, name, atype, crit, owner_username in DEMO_ASSETS:
        a = db.query(Asset).filter(Asset.asset_ip == ip).first()
        if not a:
            a = Asset(
                asset_ip=ip, name=name, asset_type=atype,
                criticality=crit, network_segment=DEMO_SEGMENT,
            )
            db.add(a)
            db.flush()
        if owner_username:
            user = _ensure_user(db, owner_username)
            a.owner_id = user.id
        assets[ip] = a
    db.commit()
    return assets


def _seed_ports(db, assets: dict[str, Asset]) -> None:
    # 修复：_seed_assets 返回的是 ip→Asset 字典，DEMO_PORTS 是 hostname→ports
    # 所以先构造 hostname→Asset 反查（也可理解为"按 hostname 取已存在 Asset"）
    assets_by_name = {a.name: a for a in assets.values()}
    for name, ports in DEMO_PORTS.items():
        a = assets_by_name.get(name)
        if not a:
            logger.warning("seed: 找不到演示资产 %s，跳过端口", name)
            continue
        for port, proto, service in ports:
            p = (
                db.query(AssetPort)
                .filter_by(asset_id=a.id, port=port, protocol=proto)
                .first()
            )
            if not p:
                p = AssetPort(
                    asset_id=a.id, asset_ip=a.asset_ip,
                    port=port, protocol=proto, state="open",
                    service=service,
                )
                db.add(p)
    db.commit()


def _seed_vulns(db, assets: dict[str, Asset]) -> None:
    vulns = []
    for cve_id, title, cvss, severity in DEMO_VULNS:
        v = db.query(Vulnerability).filter(Vulnerability.cve_id == cve_id).first()
        if not v:
            v = Vulnerability(
                cve_id=cve_id, title=title, severity=severity,
                cvss_score=cvss,
            )
            db.add(v)
            db.flush()
        vulns.append(v)

    # 给核心资产挂上漏洞
    critical_assets = [a for a in assets.values() if a.criticality == "critical"]
    for i, a in enumerate(critical_assets):
        v = vulns[i % len(vulns)]
        av = db.query(AssetVulnerability).filter_by(
            asset_id=a.id, vulnerability_id=v.id
        ).first()
        if not av:
            av = AssetVulnerability(
                asset_id=a.id, vulnerability_id=v.id,
                scanner="wazuh", status="open",
            )
            db.add(av)
    db.commit()


def _seed_business_systems(db, assets: dict[str, Asset]) -> None:
    systems = {}
    for code, name, crit in DEMO_BUSINESS_SYSTEMS:
        s = db.query(BusinessSystem).filter(BusinessSystem.code == code).first()
        if not s:
            s = BusinessSystem(code=code, name=name, criticality=crit)
            db.add(s)
            db.flush()
        systems[code] = s

    # 修复：assets 是 ip→Asset 字典，这里按 hostname 反查
    assets_by_name = {a.name: a for a in assets.values()}
    asset_to_system = {
        "srv-soc-01": "soc-platform",
        "srv-wazuh-01": "soc-platform",
        "ad-dc-01": "identity-mgmt",
        "db-core-01": "core-biz",
        "app-gateway-01": "core-biz",
        "app-business-01": "core-biz",
    }
    for asset_name, sys_code in asset_to_system.items():
        a = assets_by_name.get(asset_name)
        if not a:
            logger.warning("seed: 找不到演示资产 %s，跳过业务归属", asset_name)
            continue
        s = systems[sys_code]
        ab = db.query(AssetBusiness).filter_by(
            asset_id=a.id, system_id=s.id
        ).first()
        if not ab:
            db.add(AssetBusiness(asset_id=a.id, system_id=s.id,
                                 role="app" if sys_code == "core-biz" else "db"))
    db.commit()


def _seed_tags(db, assets: dict[str, Asset]) -> None:
    # 修复：assets 是 ip→Asset 字典，这里按 hostname 查所以先转一份
    asset_by_name = {a.name: a for a in assets.values()}
    for asset_name, tags in DEMO_TAGS.items():
        a = asset_by_name.get(asset_name)
        if not a:
            continue
        for key, value in tags:
            t = db.query(AssetTag).filter_by(
                asset_id=a.id, tag_key=key
            ).first()
            if not t:
                db.add(AssetTag(asset_id=a.id, tag_key=key, tag_value=value))
    db.commit()


def _seed_account_person(db) -> None:
    """演示账号 → 自然人映射。"""
    from app.models import User
    pairs = [("zhang@corp", "zhang"), ("li@corp", "li"), ("wang@corp", "wang"),
             ("admin@corp", None)]
    for account, username in pairs:
        user_id = None
        if username:
            user = db.query(User).filter(User.username == username).first()
            if user:
                user_id = user.id
        ap = db.query(AccountPerson).filter_by(account=account).first()
        if not ap:
            ap = AccountPerson(
                account=account, user_id=user_id,
                match_method="email" if username else "manual",
                confidence=0.9 if username else 1.0,
                verified_at=datetime.now(timezone.utc),
            )
            db.add(ap)
    db.commit()


def _seed_identity_events(db, assets: dict[str, Asset]) -> None:
    """演示登录事件流（混合内网/外网）。"""
    now = datetime.now(timezone.utc)
    soc = assets["192.168.10.10"]
    wazuh = assets["192.168.10.11"]
    ad = assets["192.168.10.12"]
    db_core = assets["192.168.10.13"]
    biz_app = assets["192.168.10.21"]

    # 内网跳板：workstation → soc
    workstation_ips = ["192.168.10.30", "192.168.10.31", "192.168.10.32"]
    accounts = ["zhang@corp", "li@corp", "wang@corp"]
    for i in range(30):
        src = workstation_ips[i % len(workstation_ips)]
        account = accounts[i % len(accounts)]
        dst_ip = soc.asset_ip
        e = db.query(IdentityEvent).filter_by(
            es_index="wazuh-demo", es_doc_id=f"evt-{i}"
        ).first()
        if not e:
            e = IdentityEvent(
                es_index="wazuh-demo", es_doc_id=f"evt-{i}",
                account=account, src_ip=src, dst_ip=dst_ip,
                success=(i % 5 != 0),
                ts=now - timedelta(hours=i),
                rule_id="5715",
            )
            db.add(e)

    # 跨主机跳板：workstation → soc → db_core
    for i in range(15):
        e = db.query(IdentityEvent).filter_by(
            es_index="wazuh-demo", es_doc_id=f"hop-{i}"
        ).first()
        if not e:
            e = IdentityEvent(
                es_index="wazuh-demo", es_doc_id=f"hop-{i}",
                account="admin@corp", src_ip=soc.asset_ip,
                dst_ip=db_core.asset_ip,
                success=True,
                ts=now - timedelta(hours=i),
                rule_id="5760",
            )
            db.add(e)

    # 外网访问
    for i in range(8):
        e = db.query(IdentityEvent).filter_by(
            es_index="wazuh-demo", es_doc_id=f"ext-{i}"
        ).first()
        if not e:
            e = IdentityEvent(
                es_index="wazuh-demo", es_doc_id=f"ext-{i}",
                account=None, src_ip=f"203.0.113.{i+1}",
                dst_ip=soc.asset_ip,
                success=True,
                ts=now - timedelta(hours=i),
                rule_id="5501",
            )
            db.add(e)

    db.commit()


def _seed_identity_bindings(db, assets: dict[str, Asset]) -> None:
    """演示账号绑定。"""
    pairs = [
        ("zhang@corp", assets["192.168.10.30"]),
        ("li@corp", assets["192.168.10.31"]),
        ("wang@corp", assets["192.168.10.32"]),
        ("admin@corp", assets["192.168.10.10"]),
    ]
    for account, a in pairs:
        b = db.query(IdentityBinding).filter_by(
            account=account, ip=a.asset_ip
        ).first()
        if not b:
            db.add(IdentityBinding(
                account=account, ip=a.asset_ip,
                asset_id=a.id, logins=50,
            ))
    db.commit()


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def reset_graph(db) -> None:
    """清空图谱相关表（保留其它数据）。"""
    db.query(GraphEdge).delete()
    db.query(GraphNode).delete()
    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Seed graph demo data")
    parser.add_argument("--reset", action="store_true",
                       help="清空图谱表后重建")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            logger.info("reset graph tables ...")
            reset_graph(db)

        logger.info("seeding demo assets ...")
        assets = _seed_assets(db)
        logger.info("seeding ports ...")
        _seed_ports(db, assets)
        logger.info("seeding vulnerabilities ...")
        _seed_vulns(db, assets)
        logger.info("seeding business systems ...")
        _seed_business_systems(db, assets)
        logger.info("seeding tags ...")
        _seed_tags(db, assets)
        logger.info("seeding account_person ...")
        _seed_account_person(db)
        logger.info("seeding identity events ...")
        _seed_identity_events(db, assets)
        logger.info("seeding identity bindings ...")
        _seed_identity_bindings(db, assets)

        logger.info("running graph builders ...")
        stats = run_all_builders(db)
        db.commit()
        for builder_name, s in stats.items():
            logger.info("  %s: %s", builder_name, s)

        # 输出图谱统计
        from app.services.graph.query import graph_stats
        gs = graph_stats(db)
        logger.info("graph stats: nodes=%d, edges=%d",
                   gs["nodes"]["total"], gs["edges"]["total"])

        logger.info("done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()