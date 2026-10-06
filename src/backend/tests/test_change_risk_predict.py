"""OH-4.10 S11 变更风险预测单测。

分层：
  - 纯评分逻辑：构造 fake per_target（无 DB/无时间线往返），秒级
  - predict 端到端：mock TimelineService.get_timeline，验证降级源/未识别
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import asyncio

from app.services.change_risk_predict import (
    HISTORY_WINDOW_DAYS,
    ChangeRiskPredictor,
)
from app.services.federation.schemas import SourceKey


def _event(severity: int, hours_ago: float = 10.0):
    return SimpleNamespace(
        severity=severity,
        ts=datetime.utcnow() - timedelta(hours=hours_ago),
        event_id=f"e-{hours_ago}-{severity}",
    )


def _target(events, related=0, impact="normal", edge="graph_edge"):
    return {
        "asset": {"name": "h1", "business_impact": impact},
        "events": events,
        "coverage_note": "",
        "related_count": related,
        "edge_source": edge,
    }


class TestScore:
    def _p(self, per_target, days=HISTORY_WINDOW_DAYS):
        # predictor 不需要 db（_score 不碰），直接构造轻量实例
        pr = ChangeRiskPredictor.__new__(ChangeRiskPredictor)
        return pr._score(per_target, days)

    def test_clean_target_low_score(self):
        score, factors = self._p([_target([])])
        # 无历史、无近期告警、normal 重要度（+10）、无影响面
        assert score == 10
        assert factors == []  # 重要度 normal 不进因子

    def test_high_density_caps_history(self):
        # 14 天 5 个高危（>4.2 阈值）→ 历史项拉满 40
        evs = [_event(13, hours_ago=h * 20) for h in range(5)]
        score, factors = self._p([_target(evs)])
        assert score >= 40
        assert any("高危事件 5" in f for f in factors)

    def test_recent_high_alert_bonus(self):
        evs = [_event(13, hours_ago=2), _event(13, hours_ago=5)]
        score, factors = self._p([_target(evs)])
        assert any("近 24h" in f for f in factors)

    def test_core_importance(self):
        score, _ = self._p([_target([], impact="core")])
        # importance = 20 * 4/4 = 20
        assert score == 20

    def test_blast_trusted_vs_fallback(self):
        trusted = self._p([_target([], related=8, edge="graph_edge")])[0]
        fallback = self._p([_target([], related=8, edge="computed_fallback")])[0]
        # trusted blast=15, fallback blast=7.5→8
        assert trusted - fallback in (7, 8)

    def test_score_bounded(self):
        evs = [_event(13, hours_ago=h) for h in range(20)]
        score, _ = self._p([_target(evs, related=20, impact="core")])
        assert score <= 100


class TestPredictRouting:
    def test_unidentified_returns_unknown(self, monkeypatch, db_session):
        # 关键词匹配不到资产：描述一个不存在的主机
        monkeypatch.setattr(
            "app.services.change_risk_predict.ia._locate_assets",
            lambda db, kw: [],
        )
        pr = ChangeRiskPredictor(db_session)
        out = asyncio.run(pr.predict("变更主机 zz-no-such-host-9k2 重启"))
        assert out["identified"] is False
        assert out["risk_score"] is None
        assert out["risk_level"] == "unknown"

    def test_degraded_sources_collected(
        self, monkeypatch, db_session
    ):
        fake_asset = SimpleNamespace(
            id="a1", asset_ip="10.0.0.1", public_ip=None,
            name="h1", business_impact="normal",
        )
        monkeypatch.setattr(
            "app.services.change_risk_predict.ia._locate_assets",
            lambda db, kw: [fake_asset],
        )
        monkeypatch.setattr(
            "app.services.change_risk_predict.ia._serialize_asset",
            lambda a: {"name": "h1", "business_impact": "normal"},
        )

        async def fake_timeline(anchor, start, end, types=None, limit=200):
            return SimpleNamespace(
                events=[],
                source_status={
                    SourceKey.PG.value: "ok",
                    SourceKey.OPENSEARCH.value: "ok",
                    SourceKey.LOKI.value: "error",
                },
                coverage_note="",
            )
        monkeypatch.setattr(
            ChangeRiskPredictor, "predict", ChangeRiskPredictor.predict
        )
        pr = ChangeRiskPredictor(db_session)
        pr.timeline = SimpleNamespace(get_timeline=fake_timeline)
        monkeypatch.setattr(
            "app.services.change_risk_predict.ia._related_assets",
            lambda db, t: {"same_segment": [], "shared_tags": [],
                           "edge_source": "graph_edge"},
        )
        out = asyncio.run(pr.predict("变更主机 h1 重启"))
        assert out["identified"] is True
        assert out["degraded_sources"] == [SourceKey.LOKI.value]
        assert out["risk_score"] == 10
