"""OH-1.4 SQLAlchemy ↔ 本体映射层单测（db_session）。"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.ontology_mapping import ClassMapping, OntologyMapping


class TestBuildMapping:
    def test_asset_instance_maps_to_orm(self, db_session: Session):
        mappings = OntologyMapping(db_session).build_mapping()
        by_id = {m.class_id: m for m in mappings}
        ai = by_id["asset-instance"]
        assert ai.mapped_to == "orm"
        assert ai.model_name == "Asset"
        assert ai.table == "soc_assets"

    def test_top_level_physical_maps_with_filter(self, db_session: Session):
        mappings = OntologyMapping(db_session).build_mapping()
        phys = next(m for m in mappings if m.class_id == "physical-asset")
        assert phys.mapped_to == "orm"
        assert "asset_type" in (phys.filter or "")

    def test_logical_asset_maps_to_graph(self, db_session: Session):
        mappings = OntologyMapping(db_session).build_mapping()
        logical = next(m for m in mappings if m.class_id == "logical-asset")
        assert logical.mapped_to == "graph"
        assert "ip" in logical.graph_node_types

    def test_person_asset_maps(self, db_session: Session):
        mappings = OntologyMapping(db_session).build_mapping()
        person = next(m for m in mappings if m.class_id == "person-asset")
        # person 同时有 User 模型 + account 图谱节点；以 ORM 为主
        assert person.model_name == "User" or "account" in person.graph_node_types


class TestValidate:
    def test_validate_distinguishes_known_and_planned(self, db_session: Session):
        out = OntologyMapping(db_session).validate()
        # 已建模型（Asset/AIAsset 等）不应报 unresolved；
        # 仅未建的规划模型（AssetComponent/Control）允许出现，这正是 validate 的价值
        unresolved = [p for p in out["problems"]
                      if p["kind"] == "unresolved_model"]
        known_leak = [
            p for p in unresolved
            if not any(name in p["detail"]
                       for name in ("AssetComponent", "Control"))
        ]
        assert known_leak == []
        assert out["checked_classes"] >= 6


class TestCount:
    def test_count_orm_class(self, db_session: Session):
        db_session.add(Asset(name="ont-c1", asset_ip="10.77.1.1"))
        db_session.commit()
        om = OntologyMapping(db_session)
        mappings = {m.class_id: m for m in om.build_mapping()}
        n = om.count_class(mappings["asset-instance"])
        assert n is not None
        assert n >= 1

    def test_count_graph_class_is_none(self, db_session: Session):
        om = OntologyMapping(db_session)
        mappings = {m.class_id: m for m in om.build_mapping()}
        assert om.count_class(mappings["logical-asset"]) is None


class TestAlignment:
    def test_alignment_summary(self, db_session: Session):
        out = OntologyMapping(db_session).class_alignment()
        assert "classes" in out
        assert out["orm_class_count"] >= 1
        assert out["graph_class_count"] >= 1
        assert "red_line" in out
        # asset-instance 行带实例计数
        ai = next(c for c in out["classes"] if c["class_id"] == "asset-instance")
        assert "instance_count" in ai
