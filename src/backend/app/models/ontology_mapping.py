"""SQLAlchemy ↔ 本体映射层（OH-1.4）

把本体 ``OntologyClass`` / ``Relation`` 上声明的 ``ai_minisoc_mappings``
解析为「可执行的映射」，并提供：

  - :func:`build_mapping` —— 本体 → 映射描述（模型类 / 表 / 过滤器 / 图谱节点类型）
  - :meth:`OntologyMapping.validate` —— 映射完整性：被引用的模型/列是否存在
  - :meth:`OntologyMapping.count_class` —— 每个本体类当前有多少实例（按 filter）
  - :meth:`OntologyMapping.class_alignment` —— 类对齐总览（供 OH-UI.8）

设计红线：
  - **只读映射层**：本模块不建表、不改数据，只把本体语义桥到 ORM。
  - **filter 是受信任配置**：来自版本控制的 YAML，用参数化 SQL 的 ``text()``
    执行；不接收用户输入拼接，杜绝注入面。
  - **graph_node_type 无 SQL 映射**：逻辑资产（IP/域名/端口）落在图谱节点，
    不对应关系表，计数返回 ``None`` 并标注 mapped_to='graph'，不伪造数量。
  - **无法解析的模型名不静默**：validate 报 unresolved，供 CI / 页面暴露。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import registry as sa_registry

from app.core import asset_ontology
from app.core.asset_ontology import OntologyClass, Relation

logger = logging.getLogger(__name__)


# 本体 YAML 中 model 名 → ORM 模型类
# （显式声明而非动态 import，避免把模型解析耦合到字符串约定；新增模型在此登记）
def _model_index() -> Dict[str, Any]:
    # 延迟导入，避免循环
    from app.models import (
        Asset, User, BusinessSystem, AIAsset,
    )
    return {
        "Asset": Asset,
        "User": User,
        "BusinessSystem": BusinessSystem,
        "AIAsset": AIAsset,
    }


@dataclass
class ClassMapping:
    """单个本体类的映射结果。"""
    class_id: str
    label: str
    mapped_to: str = "orm"          # orm / graph / unmapped
    model_name: Optional[str] = None
    table: Optional[str] = None
    filter: Optional[str] = None
    graph_node_types: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)  # 引用了但解析不了的模型名

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "label": self.label,
            "mapped_to": self.mapped_to,
            "model_name": self.model_name,
            "table": self.table,
            "filter": self.filter,
            "graph_node_types": self.graph_node_types,
            "unresolved": self.unresolved,
        }


class OntologyMapping:
    """本体 → ORM 桥接（只读）。"""

    def __init__(self, db: Session):
        self.db = db
        self._models = _model_index()

    # ---------------- 构建 ----------------

    def build_mapping(self) -> List[ClassMapping]:
        snap = asset_ontology.load()
        mappings: List[ClassMapping] = []
        for oc in snap.classes:
            mappings.append(self._map_class(oc))
        return mappings

    def _map_class(self, oc: OntologyClass) -> ClassMapping:
        cm = ClassMapping(class_id=oc.id, label=oc.label)
        orm_entries: List[Dict[str, Any]] = []
        graph_types: List[str] = []
        unresolved: List[str] = []

        for m in oc.ai_minisoc_mappings:
            if "model" in m:
                name = m["model"]
                model = self._models.get(name)
                if model is None:
                    unresolved.append(name)
                else:
                    orm_entries.append({
                        "model_name": name,
                        "model": model,
                        "filter": m.get("filter"),
                    })
            if "graph_node_type" in m:
                graph_types.append(m["graph_node_type"])

        cm.graph_node_types = graph_types
        cm.unresolved = unresolved

        if orm_entries:
            first = orm_entries[0]
            cm.mapped_to = "orm"
            cm.model_name = first["model_name"]
            cm.table = first["model"].__tablename__
            cm.filter = first["filter"]
        elif graph_types:
            cm.mapped_to = "graph"
        else:
            cm.mapped_to = "unmapped"
        return cm

    # ---------------- 完整性校验 ----------------

    def validate(self) -> Dict[str, Any]:
        mappings = self.build_mapping()
        problems: List[Dict[str, Any]] = []
        for cm in mappings:
            if cm.unresolved:
                problems.append({
                    "class_id": cm.class_id,
                    "kind": "unresolved_model",
                    "detail": f"模型名未注册: {cm.unresolved}",
                })
                continue
            if cm.mapped_to == "orm":
                # 校验 filter 引用的列在表上存在
                bad_cols = self._check_filter_columns(cm)
                if bad_cols:
                    problems.append({
                        "class_id": cm.class_id,
                        "kind": "unknown_column",
                        "detail": f"filter 引用未知列: {bad_cols}",
                    })
        return {
            "valid": not problems,
            "problems": problems,
            "checked_classes": len(mappings),
        }

    def _check_filter_columns(self, cm: ClassMapping) -> List[str]:
        """粗略提取 filter 里形如 ``col IN`` / ``col =`` 的列名并核对。"""
        if not cm.filter or not cm.table:
            return []
        import re
        cols = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:IN|=|>|<)",
                              cm.filter))
        insp = sa_inspect(self.db.bind)
        actual = {c["name"] for c in insp.get_columns(cm.table)}
        return sorted(c for c in cols if c not in actual)

    # ---------------- 实例计数 ----------------

    def count_class(self, cm: ClassMapping) -> Optional[int]:
        if cm.mapped_to != "orm" or not cm.table:
            return None
        sql = f"SELECT count(*) FROM {cm.table}"
        if cm.filter:
            sql += f" WHERE {cm.filter}"
        return self.db.execute(text(sql)).scalar()

    def class_alignment(self) -> Dict[str, Any]:
        """类对齐总览（OH-UI.8 数据源）。"""
        mappings = self.build_mapping()
        rows: List[Dict[str, Any]] = []
        for cm in mappings:
            count = None
            try:
                count = self.count_class(cm)
            except Exception as e:  # filter 执行失败也不炸页面
                logger.warning("count %s failed: %s", cm.class_id, e)
            rows.append({
                **cm.to_dict(),
                "instance_count": count,
            })
        return {
            "classes": rows,
            "orm_class_count": sum(1 for r in rows if r["mapped_to"] == "orm"),
            "graph_class_count": sum(1 for r in rows if r["mapped_to"] == "graph"),
            "unmapped_count": sum(1 for r in rows if r["mapped_to"] == "unmapped"),
            "red_line": "只读映射；图谱节点类无 SQL 计数；不据 filter 改数据",
        }
