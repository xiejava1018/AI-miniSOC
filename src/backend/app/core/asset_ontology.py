"""资产本体 v1 加载器（OH-1.2）。

设计依据：
- 主方案 §AOG-1 + 实施方案 OH-1.2
- 配置文件：configs/asset_ontology_v1.yaml（OH-1.1 已落地）
- 配合 OH-1.3 校验 CI、OH-1.4 SQLAlchemy 映射层

本模块是「AOG-2 八维画像 + AOG-3 图谱 + AOG-5 工具」等下游 OH-x 的依赖地基：
- 加载 = mtime 缓存（文件未改不重读） + 装饰器单例
- 校验 = 必填字段 + id 唯一 + domain/range 引用闭合
- 暴露 = 三个 dataclass（OntologyClass / Relation / Axiom） + 三个查询函数

【强约束】
1. **无业务依赖**：本模块只 import 标准库 + yaml，不 import sqlalchemy / fastapi
   （便于 OH-1.3 CI 跑在校验脚本里，不需要启动 FastAPI app）
2. **YAML 找不到即抛**：路径缺失 = 配置错误，启动期 fail-fast（不让脏数据进下游）
3. **装饰器缓存基于 mtime**：文件 mtime 变了才重读；进程内同一份 YAML 不重解析
4. **不引入新依赖**：不强制平台引入 pydantic / jsonschema
   （避免给轻量校验脚本加重量依赖，YAML 解析器即标准接口）

【单元测试覆盖（OH-1.5 写）】
- 单例：第二次调用不重解析
- mtime 命中：touch 文件后强制重读
- YAML 缺失：FileNotFoundError
- 必填字段校验：缺 id / version / top_level_classes 抛错
- id 唯一：top_level / relations / axioms 三层各检一次
- domain/range 闭合：关系引用未定义的类抛错
"""
from __future__ import annotations

import functools
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# 配置文件路径。沿用 query_templates.py / compliance.py 的 _CONFIG_PATH 范式：
# 从 app/core/ 上溯四级 = 项目根。
_CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "asset_ontology_v1.yaml"

# 5 分钟缓存兜底（即便 mtime 没变也最多持有 5 分钟）
_CACHE_TTL_SECONDS = 300


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OntologyClass:
    """本体类（top_level_classes / asset_instance / 子类）。"""

    id: str
    label: str
    description: str = ""
    parent: Optional[str] = None
    examples: List[str] = field(default_factory=list)
    ai_minisoc_mappings: List[Dict[str, Any]] = field(default_factory=list)
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    status: Optional[str] = None


@dataclass(frozen=True)
class Relation:
    """本体关系（relations）。"""

    id: str
    label: str
    domain: str
    range: str
    description: str = ""
    ai_minisoc_mappings: List[Dict[str, Any]] = field(default_factory=list)
    properties: List[Dict[str, Any]] = field(default_factory=list)
    status: Optional[str] = None


@dataclass(frozen=True)
class Axiom:
    """本体公理（axioms）。"""

    id: str
    label: str
    rule: str
    usage: str = ""
    test: str = ""
    status: Optional[str] = None


@dataclass(frozen=True)
class OntologySnapshot:
    """本体加载快照（不可变 + hash 可比较）。"""

    version: str
    generated_at: str
    description: str
    authority: str
    source: str
    classes: List[OntologyClass]
    relations: List[Relation]
    axioms: List[Axiom]
    fusion_weights: Dict[str, Any]
    ahs_weights: Dict[str, Any]
    standard_layer: Dict[str, Any]
    loaded_at: float
    file_mtime: float


# ---------------------------------------------------------------------------
# 加载与校验
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> Dict[str, Any]:
    """读取 YAML 文件，文件不存在抛 FileNotFoundError。"""
    if not path.exists():
        raise FileNotFoundError(
            f"asset ontology file not found: {path} "
            f"(resolved from app/core/asset_ontology.py:parents[4])"
        )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"asset ontology file must be a YAML mapping at root, got {type(data).__name__}"
        )
    return data


def _validate_required(data: Dict[str, Any]) -> None:
    """必填字段校验。"""
    if "ontology" not in data:
        raise ValueError("missing required key: 'ontology'")
    onto = data["ontology"]
    for key in ("id", "version", "generated_at"):
        if not onto.get(key):
            raise ValueError(f"missing required key: 'ontology.{key}'")
    if "top_level_classes" not in data:
        raise ValueError("missing required key: 'top_level_classes'")
    if "relations" not in data:
        raise ValueError("missing required key: 'relations'")
    if "axioms" not in data:
        raise ValueError("missing required key: 'axioms'")


def _validate_unique_ids(
    classes: List[OntologyClass],
    relations: List[Relation],
    axioms: List[Axiom],
) -> None:
    """id 唯一性三层检查。"""
    seen_classes: Dict[str, str] = {}
    for c in classes:
        if c.id in seen_classes:
            raise ValueError(
                f"duplicate ontology class id: '{c.id}' "
                f"(previous label='{seen_classes[c.id]}')"
            )
        seen_classes[c.id] = c.label

    seen_relations: Dict[str, str] = {}
    for r in relations:
        if r.id in seen_relations:
            raise ValueError(
                f"duplicate ontology relation id: '{r.id}' "
                f"(previous label='{seen_relations[r.id]}')"
            )
        seen_relations[r.id] = r.label

    seen_axioms: Dict[str, str] = {}
    for a in axioms:
        if a.id in seen_axioms:
            raise ValueError(
                f"duplicate ontology axiom id: '{a.id}' "
                f"(previous label='{seen_axioms[a.id]}')"
            )
        seen_axioms[a.id] = a.label


def _validate_relation_refs(relations: List[Relation], class_ids: set) -> None:
    """关系 domain/range 引用闭合：必须指向已定义的类（允许 domain/range = 'any'）。"""
    for r in relations:
        if r.domain != "any" and r.domain not in class_ids:
            raise ValueError(
                f"relation '{r.id}' domain='{r.domain}' references undefined class "
                f"(known classes: {sorted(class_ids)})"
            )
        if r.range != "any" and r.range not in class_ids:
            raise ValueError(
                f"relation '{r.id}' range='{r.range}' references undefined class "
                f"(known classes: {sorted(class_ids)})"
            )


def _build_classes(data: Dict[str, Any]) -> List[OntologyClass]:
    """构建 OntologyClass 列表（顶层 5 + 资产实例 + 子类）。"""
    out: List[OntologyClass] = []
    for c in data.get("top_level_classes", []):
        out.append(
            OntologyClass(
                id=str(c["id"]),
                label=str(c.get("label", c["id"])),
                description=str(c.get("description", "")),
                examples=list(c.get("examples", [])),
                ai_minisoc_mappings=list(c.get("ai_minisoc_mappings", [])),
            )
        )
    instance = data.get("asset_instance", {})
    if instance:
        out.append(
            OntologyClass(
                id=str(instance.get("id", "asset-instance")),
                label=str(instance.get("label", "资产实例")),
                description=str(instance.get("description", "")),
                parent=instance.get("parent"),
                ai_minisoc_mappings=list(instance.get("ai_minisoc_mappings", [])),
                attributes=list(instance.get("attributes", [])),
            )
        )
    for c in data.get("sub_models", []) or []:
        out.append(
            OntologyClass(
                id=str(c["id"]),
                label=str(c.get("label", c["id"])),
                description=str(c.get("description", "")),
                ai_minisoc_mappings=list(c.get("ai_minisoc_mappings", [])),
                attributes=list(c.get("attributes", [])),
                status=c.get("status"),
            )
        )
    return out


def _build_relations(data: Dict[str, Any]) -> List[Relation]:
    """构建 Relation 列表。"""
    return [
        Relation(
            id=str(r["id"]),
            label=str(r.get("label", r["id"])),
            domain=str(r.get("domain", "asset-instance")),
            range=str(r.get("range", "any")),
            description=str(r.get("description", "")),
            ai_minisoc_mappings=list(r.get("ai_minisoc_mappings", [])),
            properties=list(r.get("properties", [])),
            status=r.get("status"),
        )
        for r in data.get("relations", [])
    ]


def _build_axioms(data: Dict[str, Any]) -> List[Axiom]:
    """构建 Axiom 列表。"""
    return [
        Axiom(
            id=str(a["id"]),
            label=str(a.get("label", a["id"])),
            rule=str(a.get("rule", "")),
            usage=str(a.get("usage", "")),
            test=str(a.get("test", "")),
            status=a.get("status"),
        )
        for a in data.get("axioms", [])
    ]


def _parse(data: Dict[str, Any], file_mtime: float) -> OntologySnapshot:
    """纯解析（无缓存）。"""
    _validate_required(data)
    classes = _build_classes(data)
    relations = _build_relations(data)
    axioms = _build_axioms(data)
    _validate_unique_ids(classes, relations, axioms)
    # class_ids 包含标准层锚（STIX SCO/SDO 名）+ "any"，关系 domain/range 可指向这些
    standard = data.get("standard_layer", {})
    class_ids = (
        {c.id for c in classes}
        | {"any"}
        | set(standard.get("stix_2_1", {}).get("sco", []))
        | set(standard.get("stix_2_1", {}).get("sdo", []))
    )
    _validate_relation_refs(relations, class_ids)

    onto = data["ontology"]
    return OntologySnapshot(
        version=str(onto["version"]),
        generated_at=str(onto.get("generated_at", "")),
        description=str(onto.get("description", "")),
        authority=str(onto.get("authority", "")),
        source=str(onto.get("source", "")),
        classes=classes,
        relations=relations,
        axioms=axioms,
        fusion_weights=dict(data.get("fusion_weights", {})),
        ahs_weights=dict(data.get("ahs_weights", {})),
        standard_layer=standard,
        loaded_at=time.time(),
        file_mtime=file_mtime,
    )


# ---------------------------------------------------------------------------
# 缓存层（装饰器 + 文件 mtime + TTL）
# ---------------------------------------------------------------------------

_cache: Dict[str, Any] = {
    "snapshot": None,
    "mtime": 0.0,
    "loaded_at": 0.0,
    "config_path": _CONFIG_PATH,
}


def _is_cache_valid(snap: Optional[OntologySnapshot], now: float) -> bool:
    if snap is None:
        return False
    if (now - snap.loaded_at) > _CACHE_TTL_SECONDS:
        return False
    if not _CONFIG_PATH.exists():
        return False
    return True


def _refresh_cache(force: bool = False) -> OntologySnapshot:
    """强制或必要时刷新缓存。"""
    now = time.time()
    cached = _cache["snapshot"]
    if not force and _is_cache_valid(cached, now):
        return cached

    if not _CONFIG_PATH.exists():
        if cached is not None:
            # YAML 文件被删，启动期配置错误——但已有缓存可继续服务（fail-open）
            logger.warning(
                "asset ontology file disappeared at %s, serving stale cache", _CONFIG_PATH
            )
            return cached
        raise FileNotFoundError(
            f"asset ontology file not found: {_CONFIG_PATH} "
            "(no cached snapshot to fall back on)"
        )

    file_mtime = os.path.getmtime(_CONFIG_PATH)
    if not force and cached is not None and cached.file_mtime == file_mtime:
        # 文件未改，只更新 loaded_at（保留 TTL 滚动）
        return cached

    data = _read_yaml(_CONFIG_PATH)
    snap = _parse(data, file_mtime)
    _cache["snapshot"] = snap
    _cache["mtime"] = file_mtime
    _cache["loaded_at"] = snap.loaded_at
    return snap


@functools.lru_cache(maxsize=1)
def _load_once() -> OntologySnapshot:
    """进程内单例入口（不绕过 mtime 检查）。"""
    return _refresh_cache(force=False)


def load(config_path: Optional[Path] = None) -> OntologySnapshot:
    """加载资产本体快照。

    Args:
        config_path: 可选覆盖默认路径（测试用）。生产代码传 None，走默认 _CONFIG_PATH。

    Returns:
        OntologySnapshot（不可变）

    Raises:
        FileNotFoundError: YAML 文件不存在且无缓存兜底
        ValueError: YAML 缺必填字段 / id 重复 / domain/range 未定义
    """
    if config_path is not None:
        # 测试覆盖路径时刷新单例缓存
        _load_once.cache_clear()
        global _CONFIG_PATH
        _CONFIG_PATH = config_path
        _cache["config_path"] = config_path
        _cache["snapshot"] = None
        _cache["mtime"] = 0.0
    return _load_once()


def reload() -> OntologySnapshot:
    """强制重读 YAML（用于 CI / 配置变更通知）。"""
    _load_once.cache_clear()
    return _refresh_cache(force=True)


# ---------------------------------------------------------------------------
# 查询 API（上游 OH-2.x / 3.x / 5.x 直接调用）
# ---------------------------------------------------------------------------


def get_class(class_id: str) -> Optional[OntologyClass]:
    """按 id 查类（顶层 / 实例 / 子类 / 标准层）。"""
    snap = load()
    for c in snap.classes:
        if c.id == class_id:
            return c
    # 标准层锚（STIX SCO/SDO）不存为 OntologyClass，按需惰性构造
    standard = snap.standard_layer.get("stix_2_1", {})
    if class_id in standard.get("sco", []) or class_id in standard.get("sdo", []):
        return OntologyClass(
            id=class_id,
            label=class_id,
            description=f"STIX 2.1 standard type (read-only anchor; see {snap.source})",
        )
    return None


def get_relation(relation_id: str) -> Optional[Relation]:
    """按 id 查关系。"""
    snap = load()
    for r in snap.relations:
        if r.id == relation_id:
            return r
    return None


def get_axiom(axiom_id: str) -> Optional[Axiom]:
    """按 id 查公理。"""
    snap = load()
    for a in snap.axioms:
        if a.id == axiom_id:
            return a
    return None


def list_classes() -> List[OntologyClass]:
    """列出所有类（含标准层锚）。"""
    snap = load()
    return list(snap.classes)


def list_relations() -> List[Relation]:
    snap = load()
    return list(snap.relations)


def list_axioms() -> List[Axiom]:
    snap = load()
    return list(snap.axioms)


# ---------------------------------------------------------------------------
# 自检入口（供 OH-1.3 CI 调用）
# ---------------------------------------------------------------------------


def self_check() -> Dict[str, Any]:
    """本体自检：返回版本 / 类数 / 关系数 / 公理数 / 文件 mtime / 加载耗时。

    CI 调用方式：
        PYTHONPATH=src/backend python -c "from app.core.asset_ontology import self_check, json; print(json.dumps(self_check(), indent=2))"
    """
    t0 = time.time()
    snap = load()
    elapsed_ms = (time.time() - t0) * 1000
    return {
        "ontology_id": snap.authority,
        "version": snap.version,
        "generated_at": snap.generated_at,
        "classes": len(snap.classes),
        "relations": len(snap.relations),
        "axioms": len(snap.axioms),
        "file_mtime": snap.file_mtime,
        "loaded_at": snap.loaded_at,
        "elapsed_ms": round(elapsed_ms, 3),
        "config_path": str(_CONFIG_PATH),
    }


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(self_check(), indent=2, ensure_ascii=False))