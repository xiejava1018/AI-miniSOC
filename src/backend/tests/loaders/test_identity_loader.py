"""OH-2.1 T2 — ① 身份维 loader 单测。"""
from __future__ import annotations

import pytest

from app.services.asset_profile import AssetIdentity, EvidenceItem
from app.services.asset_profile.loaders.identity import load_identity


class TestLoadIdentity:
    """T2 — ① 身份维 loader 单测（5 例）。"""

    def test_full_seeded_returns_all_fields(self, db_session, sample_asset_for_profile):
        """完整 seed → 所有字段都填，identity_confidence=1.0（IdentityBinding 行 ≥1）。"""
        result = load_identity(db_session, sample_asset_for_profile)
        # db_session 模式：AssetSource.source_id + Asset 字段 都能填满
        assert isinstance(result, AssetIdentity)
        assert result.source_id == "W-NET-001"
        assert result.data_source == "wazuh"
        assert result.wazuh_agent_id == "001"
        assert result.mac_address == "aa:bb:cc:dd:ee:01"
        assert result.hostname == "prod-server-1"
        # confidence ≥ 0.5（asset.source_id 非空）

    def test_minimal_asset_low_confidence(self, minimal_asset):
        """最小 asset（无 source_id/wazuh/mac）→ identity_confidence=0.0。"""
        result = load_identity(None, minimal_asset)  # type: ignore[arg-type]
        assert isinstance(result, AssetIdentity)
        assert result.source_id is None
        assert result.wazuh_agent_id is None
        assert result.mac_address is None
        # 无 source_id/wazuh_agent_id → confidence 0.0
        # 但仍可能 evidence 列表

    def test_evidence_has_source(self, sample_asset_for_profile):
        """evidence.source 必填 = soc_assets。"""
        result = load_identity(None, sample_asset_for_profile)  # type: ignore[arg-type]
        assert len(result.evidence) >= 1
        ev = result.evidence[0]
        assert isinstance(ev, EvidenceItem)
        assert ev.source == "soc_assets"
        assert 0.0 <= ev.confidence <= 1.0

    def test_bindings_count_with_seed(self, db_session, sample_asset_for_profile):
        """IdentityBinding ≥1 → bindings_count ≥1（用真 db_session 走 ORM 查询）。"""
        result = load_identity(db_session, sample_asset_for_profile)
        assert result.identity_bindings_count >= 1
        # confidence ≥ 0.8（1 binding） 或 1.0（2+）
        assert result.identity_confidence >= 0.8

    def test_hostname_fallback_to_binding_account(self, db_session):
        """Asset.name 空时，hostname fallback 到最近 IdentityBinding.account。"""
        from datetime import datetime, timezone
        from app.models import Asset, IdentityBinding

        NOW = datetime.now(timezone.utc)
        a = Asset(
            network_segment="X", asset_ip="10.0.0.1", asset_status="online",
            name=None,
            created_at=NOW, updated_at=NOW,
        )
        db_session.add(a)
        db_session.flush()
        db_session.add(IdentityBinding(
            asset_id=a.id, account="alice", ip="10.0.0.1",
            logins=1, first_seen=NOW, last_seen=NOW,
        ))
        db_session.commit()
        db_session.refresh(a)

        result = load_identity(db_session, a)
        assert result.hostname == "alice"