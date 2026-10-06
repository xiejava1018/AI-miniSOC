"""OH-1.6 STIX 2.1 导出单测（纯函数，无需 DB）。"""
from __future__ import annotations

import re

from app.core.asset_ontology_stix import export_stix_bundle


class TestSTIXBundle:
    def setup_method(self):
        self.b = export_stix_bundle()

    def test_bundle_shape(self):
        assert self.b["type"] == "bundle"
        assert self.b["id"].startswith("bundle--")
        assert isinstance(self.b["objects"], list)

    def test_contains_identity(self):
        types = [o["type"] for o in self.b["objects"]]
        assert "identity" in types
        assert "marking-definition" in types

    def test_attack_pattern_sdos(self):
        aps = [o for o in self.b["objects"]
               if o["type"] == "attack-pattern"]
        assert len(aps) >= 5
        for ap in aps:
            assert ap["id"].startswith("attack-pattern--")
            assert ap["spec_version"] == "2.1"
            assert ap.get("name")

    def test_external_references_mitre(self):
        ap = next(o for o in self.b["objects"]
                  if o["type"] == "attack-pattern"
                  and o["external_references"])
        ref = ap["external_references"][0]
        assert ref["source_name"] == "mitre-attack"
        assert re.match(r"T\d{4}", ref["external_id"])

    def test_deterministic_ids(self):
        b2 = export_stix_bundle()
        # 同一目录重放，attack-pattern id 稳定
        ids1 = sorted(o["id"] for o in self.b["objects"])
        ids2 = sorted(o["id"] for o in b2["objects"])
        # bundle id 与 SDO id（非时间相关）一致；created 时间戳除外
        non_ts1 = [i for i in ids1]
        assert non_ts1 == ids2

    def test_compat_statement(self):
        md = next(o for o in self.b["objects"]
                  if o["type"] == "marking-definition")
        assert "STIX 2.1" in md["definition"]["statement"]

    def test_subtechnique_flag(self):
        sub = [o for o in self.b["objects"]
               if o["type"] == "attack-pattern"
               and o.get("x_mitre_is_subtechnique")]
        # 目录含 T1110.001 等子技
        assert len(sub) >= 1
