"""OH-4.13 S13 AI 资产建模单测（db_session）。"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.ai_asset import AIAssetKind, AIAssetRisk, AIAssetStatus
from app.services.ai_asset_service import (
    AIAssetService,
    CredentialPlaintextError,
)


class TestCreate:
    def test_basic(self, db_session: Session):
        a = AIAssetService(db_session).create(
            kind=AIAssetKind.MODEL, name="gpt-internal",
            provider="openai", version="gpt-4o",
            owner="bob", business_unit="ai-platform",
        )
        assert a.id is not None
        assert a.kind == AIAssetKind.MODEL
        assert a.status == AIAssetStatus.REGISTERED

    def test_credential_forbidden_keys(self, db_session: Session):
        with pytest.raises(CredentialPlaintextError) as exc:
            AIAssetService(db_session).create(
                kind=AIAssetKind.CREDENTIAL,
                name="openai-key-1",
                details={"api_key": "sk-xxx", "scope": "internal"},
            )
        assert "api_key" in str(exc.value)

    def test_credential_metadata_allowed(self, db_session: Session):
        a = AIAssetService(db_session).create(
            kind=AIAssetKind.CREDENTIAL,
            name="openai-key-meta",
            details={"key_id": "vault:openai#prod", "scope": "internal"},
        )
        assert a.details["scope"] == "internal"

    def test_shadow_status(self, db_session: Session):
        a = AIAssetService(db_session).create(
            kind=AIAssetKind.MODEL, name="shadow-1",
            status=AIAssetStatus.SHADOW,
            risk_level=AIAssetRisk.HIGH,
        )
        assert a.status == AIAssetStatus.SHADOW
        assert a.risk_level == AIAssetRisk.HIGH


class TestDashboard:
    def test_counts(self, db_session: Session):
        svc = AIAssetService(db_session)
        svc.create(kind=AIAssetKind.MODEL, name="m1")
        svc.create(kind=AIAssetKind.MODEL, name="m2",
                   status=AIAssetStatus.SHADOW)
        svc.create(kind=AIAssetKind.DATA, name="d1")
        svc.create(kind=AIAssetKind.AGENT, name="ag1",
                   status=AIAssetStatus.SHADOW)
        svc.create(kind=AIAssetKind.TOOL, name="t1")

        out = svc.dashboard()
        assert out["total"] == 5
        assert out["by_kind"]["model"] == 2
        # shadow 在 model/data/agent 三类中，tool 不计
        assert out["shadow_ai_count"] == 2
        assert "red_line" in out


class TestList:
    def test_filter_by_kind_and_status(self, db_session: Session):
        svc = AIAssetService(db_session)
        svc.create(kind=AIAssetKind.MODEL, name="m1")
        svc.create(kind=AIAssetKind.MODEL, name="m2",
                   status=AIAssetStatus.SANCTIONED)
        svc.create(kind=AIAssetKind.DATA, name="d1")
        db_session.commit()

        assert len(svc.list(kind=AIAssetKind.MODEL)) == 2
        assert len(svc.list(status=AIAssetStatus.SANCTIONED)) == 1
        assert len(svc.list()) == 3
