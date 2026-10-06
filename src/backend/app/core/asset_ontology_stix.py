"""STIX 2.1 兼容导出（OH-1.6）

把平台的技战术目录（OH-4.4 ``configs/attack_patterns.yaml`` 离线种子）
导出为 **STIX 2.1 Bundle**（JSON）。

为什么只导技战术目录：
  - 现网无外联 ATT&CK / STIX feed 通路，attack_patterns.yaml 是平台自己的
    权威离线目录；把它转成 STIX bundle，可对接外部 TAXII/威胁情报工作流。
  - 实时资产 / observed-data 属于业务数据面，不在「本体/目录导出」范围。

设计红线：
  - **不引入 stix2 库**：bundle 结构简单（id/type/created/modified +
    attack-pattern SDO + identity + marking-definition），直接构造 dict；
    id 用符合 STIX 规范的 UUIDv5（确定性、可重放）。
  - **只标注兼容，不冒充认证**：输出遵循 STIX 2.1 字段约定，但未经
    OASIS STIX 2.1 一致性测试；在 bundle description 诚实声明。
  - **纯只读**：不读业务数据库，只消费 YAML 目录。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "attack_patterns.yaml"

# STIX 固定命名空间 UUID（用于 UUIDv5 生成确定性 id）
_STIX_NS = uuid.UUID("d4d9502a-1e9b-4d58-aa23-3a92555d83e4")

_IDENTITY_ID = "identity--" + str(uuid.uuid5(_STIX_NS, "ai-minisoc-identity"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _stix_uuid(prefix: str, key: str) -> str:
    return f"{prefix}--" + str(uuid.uuid5(_STIX_NS, key))


def _load_catalog() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"技战术目录缺失: {_CONFIG_PATH}")
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def export_stix_bundle() -> Dict[str, Any]:
    catalog = _load_catalog()
    ts = _now()
    objects: List[Dict[str, Any]] = []

    # 1) Identity（平台自己）
    objects.append({
        "type": "identity",
        "spec_version": "2.1",
        "id": _IDENTITY_ID,
        "created": ts,
        "modified": ts,
        "name": "AI-miniSOC",
        "identity_class": "organization",
    })

    # 2) Attack Pattern SDO（每条技战术）
    for tech in catalog.get("techniques", []):
        tid = tech.get("technique_id")
        refs: List[Dict[str, Any]] = []
        if tid:
            refs.append({
                "source_name": "mitre-attack",
                "external_id": tid,
                "url": tech.get("url") or
                       f"https://attack.mitre.org/techniques/{tid}/",
            })
        objects.append({
            "type": "attack-pattern",
            "spec_version": "2.1",
            "id": _stix_uuid("attack-pattern", tid or tech.get("name", "")),
            "created": ts,
            "modified": ts,
            "name": tech.get("name"),
            "external_references": refs,
            "x_mitre_is_subtechnique": bool(tid and "." in tid),
            "labels": ["attack-pattern"],
        })

    # 3) Marking definition（兼容性声明）
    marking_id = "marking-definition--" + str(
        uuid.uuid5(_STIX_NS, "ai-minisoc-compat"))
    objects.append({
        "type": "marking-definition",
        "spec_version": "2.1",
        "id": marking_id,
        "created": ts,
        "definition_type": "statement",
        "definition": {
            "statement":
                "STIX 2.1-compatible output; not certified against the "
                "OASIS STIX 2.1 conformance suite."
        },
    })

    return {
        "type": "bundle",
        "id": _stix_uuid("bundle", f"attack-patterns:{catalog.get('version')}"),
        "objects": objects,
    }
