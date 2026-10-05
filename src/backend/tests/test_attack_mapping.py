"""OH-4.4 ATT&CK 映射服务单测（db_session + mock 告警）。"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.attack_pattern import (
    MATCH_RULE_GROUPS,
    MATCH_RULE_ID,
    AlertAttackMapping,
    AttackPattern,
)
from app.services import attack_mapping as am


@pytest.fixture()
def seeded(db_session: Session):
    """直接用 YAML 种子同步（覆盖两表 upsert 路径）。"""
    out = am.sync_from_yaml(db_session)
    assert out["patterns"] > 0 and out["mappings"] > 0
    return db_session


class TestSync:
    def test_idempotent(self, seeded: Session):
        out1 = am.sync_from_yaml(seeded)
        # 二次同步不重复（唯一约束 upsert）
        counts = seeded.query(AlertAttackMapping).count()
        am.sync_from_yaml(seeded)
        assert seeded.query(AlertAttackMapping).count() == counts
        assert out1["mappings"] > 0

    def test_manual_override_preserved(self, seeded: Session):
        # 改一条为 manual，重新同步后不被覆盖
        m = seeded.query(AlertAttackMapping).filter(
            AlertAttackMapping.match_type == MATCH_RULE_ID,
            AlertAttackMapping.match_value == "5710",
        ).first()
        m.confidence = 0.99
        m.manual_override = "1"
        seeded.commit()

        am.sync_from_yaml(seeded)
        seeded.refresh(m)
        assert m.confidence == 0.99


class TestMapRule:
    def test_exact_rule_id_high_confidence(self, seeded: Session):
        hits = am.map_rule(seeded, "5710", None)
        assert hits and hits[0]["technique_id"] == "T1110.001"
        assert hits[0]["confidence"] == 0.9

    def test_group_prefix_lower_confidence(self, seeded: Session):
        hits = am.map_rule(seeded, None, ["syscheck"])
        assert hits
        assert any(h["technique_id"] == "T1562.001" for h in hits)
        assert all(h["match_type"] == MATCH_RULE_GROUPS for h in hits)

    def test_unmapped_returns_empty(self, seeded: Session):
        assert am.map_rule(seeded, "99999", ["no-such-group"]) == []

    def test_sorted_by_confidence(self, seeded: Session):
        # 5710 精确 + sshd 组同时命中 → 精确在前
        hits = am.map_rule(seeded, "5710", ["sshd"])
        confs = [h["confidence"] for h in hits]
        assert confs == sorted(confs, reverse=True)

    def test_no_input(self, seeded: Session):
        assert am.map_rule(seeded, None, None) == []


class TestAttackChain:
    def test_chain(self, seeded: Session, monkeypatch):
        from app.services import alert_query as aq

        alert = {
            "_id": "a1",
            "@timestamp": "2026-10-05T00:00:00Z",
            "rule": {"id": "5710", "description": "sshd brute",
                     "level": 10, "groups": ["sshd"]},
            "agent": {"id": "001", "name": "web01", "ip": "10.0.0.1"},
        }
        monkeypatch.setattr(
            aq.AlertQueryService, "get_alert_by_id",
            lambda self, aid: alert,
        )
        monkeypatch.setattr(
            aq.AlertQueryService, "_find_asset",
            lambda self, agent_id=None, agent_ip=None: None,
        )

        out = am.attack_chain(seeded, "a1")
        assert out["mapped"] is True
        assert out["alert"]["rule_id"] == "5710"
        assert out["techniques"][0]["technique_id"] == "T1110.001"
        assert out["linked_asset"] is None
        assert out["business_systems"] == []

    def test_missing_alert_raises(self, seeded: Session, monkeypatch):
        from app.services import alert_query as aq
        monkeypatch.setattr(
            aq.AlertQueryService, "get_alert_by_id",
            lambda self, aid: None,
        )
        with pytest.raises(ValueError):
            am.attack_chain(seeded, "nope")
