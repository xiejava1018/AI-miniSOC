#!/usr/bin/env python3
"""
Seed 数据源配置到 soc_data_sources 表（任何 dev / 测试 / 生产新环境一行起步）

依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.4.1 / §11.2

数据源定义在 .env 中的 7 个键：
    WAZUH_API_URL, WAZUH_API_USERNAME, WAZUH_API_PASSWORD
    OPENSEARCH_URL, OPENSEARCH_USER, OPENSEARCH_PASSWORD
    LOKI_API_URL  (注：102 旧版用 LOKI_URL，二者皆支持，向后兼容)

策略：
- 数据源在 DB（soc_data_sources），auth_secret 走 Fernet 加密
- 本脚本是「DB 没记录时从 .env 一次性写」的种子；后续 UI 改 → 不应再回写 .env
- 幂等：source_code 已存在则跳过；不会覆盖 UI 后续修改
- 同 .env.example 注释说明：本脚本与 .env 必须配对；删 .env 键前先迁 DB

用法:
    cd src/backend
    ../../venv/bin/python scripts/seed_datasources.py
    ../../venv/bin/python scripts/seed_datasources.py --update   # 强制用 .env 覆盖
    ../../venv/bin/python scripts/seed_datasources.py --types    # 列出支持的 source_type

注意：
- 必须先在 Settings 中把 WAZUH_API_USERNAME/PASSWORD 设为 Optional 才能跑（commit 157f4d1）。
  否则 .env 缺这两个键时 Settings 启动会校验失败。
- 任何 dev 环境首次启动时跑一次即可，重复跑无副作用（已存在就跳过）。
"""
import argparse
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.data_source import DataSource
from app.models.user import User
from app.schemas.data_source import DataSourceCreate
from app.services.data_source_resolver import data_source_resolver
from app.services.data_source_service import DataSourceService


# source_type → (auth_type, endpoint 字段, user 字段, secret 字段)
# 缺失字段则 auth_type='none'，account/secret 留空
SOURCE_DEFS = [
    dict(
        source_code="wazuh-prod",
        source_type="wazuh",
        name="生产 Wazuh",
        endpoint_attr="WAZUH_API_URL",
        auth_type="basic",
        user_attr="WAZUH_API_USERNAME",
        secret_attr="WAZUH_API_PASSWORD",
    ),
    dict(
        source_code="opensearch-prod",
        source_type="opensearch",
        name="Wazuh Indexer",
        endpoint_attr="OPENSEARCH_URL",
        auth_type="basic",
        user_attr="OPENSEARCH_USER",
        secret_attr="OPENSEARCH_PASSWORD",
    ),
    dict(
        source_code="loki-prod",
        source_type="loki",
        name="主 Loki",
        # 历史 .env 两种命名都支持（LOKI_URL / LOKI_API_URL）
        endpoint_attr=("LOKI_API_URL", "LOKI_URL"),
        auth_type="none",
        user_attr=None,
        secret_attr=None,
    ),
]


def get_env_value(attr_spec):
    """attr_spec 可为 str 或 tuple（多个候选名，按顺序取第一个有值的）。"""
    if isinstance(attr_spec, str):
        return getattr(settings, attr_spec, None) or os.environ.get(attr_spec)
    for name in attr_spec:
        v = getattr(settings, name, None) or os.environ.get(name)
        if v:
            return v
    return None


def list_types():
    print("=== 当前 .env 中识别到的源 ===")
    for cfg in SOURCE_DEFS:
        endpoint = get_env_value(cfg["endpoint_attr"])
        user = get_env_value(cfg["user_attr"]) if cfg["user_attr"] else None
        secret_set = bool(get_env_value(cfg["secret_attr"])) if cfg["secret_attr"] else False
        ok = "✓" if endpoint else "✗"
        print(
            f"  {ok} {cfg['source_code']:<20s} type={cfg['source_type']:<11s} "
            f"endpoint={endpoint or '(missing)'}  user={user}  secret={'***' if secret_set else '(none)'}"
        )


def seed(force_update: bool = False):
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            print("FATAL: admin user not found; run init_system_data.py first")
            sys.exit(1)
        svc = DataSourceService(db)

        created, skipped, updated, failed = 0, 0, 0, 0
        for cfg in SOURCE_DEFS:
            endpoint = get_env_value(cfg["endpoint_attr"])
            if not endpoint:
                print(f"  -- 跳过 {cfg['source_code']}: .env 缺 {cfg['endpoint_attr']}")
                skipped += 1
                continue

            user = get_env_value(cfg["user_attr"]) if cfg["user_attr"] else None
            secret = get_env_value(cfg["secret_attr"]) if cfg["secret_attr"] else None
            auth_type = cfg["auth_type"]

            # 无 auth_type 但 env 给了 user/secret 时升级为 basic
            if auth_type == "none" and (user or secret):
                auth_type = "basic"

            existing = (
                db.query(DataSource)
                .filter(DataSource.source_code == cfg["source_code"])
                .first()
            )

            if existing and not force_update:
                print(
                    f"  -- 跳过 {cfg['source_code']}: 已存在 id={existing.id}（--update 可强制覆盖）"
                )
                skipped += 1
                continue

            if existing and force_update:
                # 走 update 路径，保留审计 + resolver invalidate
                from app.schemas.data_source import DataSourceUpdate

                payload = DataSourceUpdate(
                    name=cfg["name"],
                    endpoint=endpoint,
                    auth_type=auth_type,
                    auth_username=user,
                    auth_secret=secret,
                    verify_ssl=False,
                    timeout_seconds=30,
                    retry_times=3,
                    retry_backoff_seconds=2,
                    is_default=True,
                    enabled=True,
                )
                svc.update(existing.id, payload, operator_id=admin.id, operator_ip="127.0.0.1")
                print(f"  ↻ 更新 {cfg['source_code']}: id={existing.id} endpoint={endpoint}")
                updated += 1
                continue

            # 全新写入
            payload = DataSourceCreate(
                source_code=cfg["source_code"],
                source_type=cfg["source_type"],
                name=cfg["name"],
                endpoint=endpoint,
                auth_type=auth_type,
                auth_username=user,
                auth_secret=secret,
                verify_ssl=False,
                timeout_seconds=30,
                retry_times=3,
                retry_backoff_seconds=2,
                is_default=True,
                enabled=True,
            )
            try:
                ds = svc.create(payload, operator_id=admin.id, operator_ip="127.0.0.1")
                print(
                    f"  + 创建 {cfg['source_code']}: id={ds.id} type={ds.source_type} "
                    f"endpoint={ds.endpoint} has_secret={bool(ds.auth_secret)}"
                )
                created += 1
            except Exception as e:
                print(f"  ✗ 失败 {cfg['source_code']}: {e}")
                failed += 1

        print()
        print(f"=== 完成: created={created} updated={updated} skipped={skipped} failed={failed} ===")

        # 让本次进程的 resolver cache 失效
        data_source_resolver.invalidate()
        print("resolver cache invalidated")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--update",
        action="store_true",
        help="强制用 .env 覆盖已存在的记录（默认跳过）",
    )
    parser.add_argument(
        "--types",
        action="store_true",
        help="只列出从 .env 识别到的源，不写库",
    )
    args = parser.parse_args()

    if args.types:
        list_types()
        return
    seed(force_update=args.update)


if __name__ == "__main__":
    main()
