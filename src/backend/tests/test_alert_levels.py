"""分级阈值统一（app/core/alert_levels.py）回归测试

2026-08-22 两轮修复的签字条件（见 docs/design/2026-08-22-alert-level-threshold-unification-patch.md §5）：
1. 全项目只有一处阈值真相
2. _level_to_severity(12) ≠ critical（alert_incident_service 曾硬写 12/9/6）
3. _heuristic_verdict level 7-9 → P2（第一轮修复曾留 off-by-one）
4. P 级与 severity 链互逆自洽
"""
import pytest

from app.core.alert_levels import (
    LEVEL_CRITICAL, LEVEL_HIGH, LEVEL_MEDIUM, LEVEL_LOW,
    SEVERE_LEVEL, level_to_severity, level_to_priority,
)


@pytest.mark.unit
class TestCentralModule:
    def test_constants(self):
        assert (LEVEL_CRITICAL, LEVEL_HIGH, LEVEL_MEDIUM, LEVEL_LOW) == (13, 10, 7, 4)

    def test_severe_level_semantically_distinct(self):
        # SEVERE_LEVEL 是"是否打扰人"的通知阈值，与 LEVEL_HIGH（风险分级）语义不同
        assert SEVERE_LEVEL == 12
        assert SEVERE_LEVEL != LEVEL_HIGH

    @pytest.mark.parametrize("level,want", [
        (13, "critical"), (15, "critical"),
        (12, "high"), (10, "high"),
        (9, "medium"), (7, "medium"),
        (6, "low"), (4, "low"), (3, "low"),
        (None, "low"), ("abc", "low"), ("12", "high"),
    ])
    def test_level_to_severity(self, level, want):
        assert level_to_severity(level) == want

    @pytest.mark.parametrize("level,want", [
        (13, "P0"), (11, "P1"), (10, "P1"), (8, "P2"), (7, "P2"), (5, "P3"),
    ])
    def test_level_to_priority(self, level, want):
        assert level_to_priority(level) == want


@pytest.mark.unit
class TestCallersAligned:
    """调用方与中央模块对齐（防回退的持久化断言）。"""

    def test_incident_severity_delegates(self):
        from app.services.alert_incident_service import _level_to_severity
        # 曾硬写 12/9/6：12 被标 critical、9 被标 high、6 被标 medium
        assert _level_to_severity(12) == "high"
        assert _level_to_severity(9) == "medium"
        assert _level_to_severity(6) == "low"
        assert _level_to_severity(13) == "critical"
        assert _level_to_severity(7) == "medium"

    def test_priority_severity_roundtrip(self):
        """P 级路径与 severity 路径对同一 level 结论必须一致（曾出现
        level-9 簇：走缓存得 medium、不走缓存 fallback 得 high 的矛盾）。"""
        from app.services.alert_incident_service import _PRIORITY_TO_SEVERITY
        from app.services.alert_incident_service import _level_to_severity
        for lv in (13, 12, 10, 9, 7, 6, 4, 3):
            assert _PRIORITY_TO_SEVERITY[level_to_priority(lv)] == _level_to_severity(lv), lv

    def test_heuristic_verdict_aligned(self):
        from app.services.ai_analysis import AIAnalysisService
        svc = AIAnalysisService.__new__(AIAnalysisService)
        # 第一轮修复曾留 off-by-one：13→P1（应 P0）、7-9→P3（应 P2）
        assert svc._heuristic_verdict({"level_max": 13, "count": 1})["priority"] == "P0"
        assert svc._heuristic_verdict({"level_max": 9, "count": 1})["priority"] == "P2"
        assert svc._heuristic_verdict({"level_max": 7, "count": 1})["priority"] == "P2"
        assert svc._heuristic_verdict({"level_max": 10, "count": 1})["priority"] == "P1"
        # P0/P1（critical/high 簇）建议建事件；P2/P3 不建议
        assert svc._heuristic_verdict({"level_max": 13, "count": 1})["suggest_incident"] is True
        assert svc._heuristic_verdict({"level_max": 10, "count": 1})["suggest_incident"] is True
        assert svc._heuristic_verdict({"level_max": 8, "count": 1})["suggest_incident"] is False
