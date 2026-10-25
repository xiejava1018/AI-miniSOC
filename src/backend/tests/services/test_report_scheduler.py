"""
F2.2 报告自动生成调度器测试（weekly / monthly）

背景
----
此前 weekly / monthly 两种报告类型**没有任何调度器**——只能用户在报告列表页
手动点「生成」。文章《12 AI 安全报告与主动推送》里写的是「定时生成」，
实现与描述不符。本测试锁定新调度器的行为。

覆盖：
- 周期 key：ISO 周 / 自然月，跨年边界
- 到期判定：生成日 / 生成时刻 / 开关 / 幂等
- 配置外置：soc_system_config[reports] 覆盖
- 幂等：同周期不重复生成
- 边界：月报日配置超界（29/30/31）、生成时刻未到
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.services.report_scheduler import (  # noqa: E402
    _last_day_of_month,
    is_due,
    monthly_period_key,
    period_key,
    weekly_period_key,
)


# ---------------------------------------------------------------------------
# 周期 key
# ---------------------------------------------------------------------------

def test_weekly_period_key_is_iso_week():
    d = datetime(2026, 10, 19)  # 周一
    assert weekly_period_key(d) == "2026-W43"


def test_weekly_period_key_same_within_a_week():
    monday = datetime(2026, 10, 19)
    sunday = datetime(2026, 10, 25)
    assert weekly_period_key(monday) == weekly_period_key(sunday)


def test_weekly_period_key_differs_across_weeks():
    assert weekly_period_key(datetime(2026, 10, 19)) != \
        weekly_period_key(datetime(2026, 10, 26))


def test_weekly_period_key_year_boundary():
    """跨年时 ISO 周归属唯一，不会出现同一周两个 key。

    2026-12-31（周四）与 2027-01-01（周五）同属 ISO 周 2026-W53——
    这正是 ISO 周的优势：不会像「自然周」那样把年末年初拆成两周，
    导致一份周报被算成两份。
    """
    dec31 = datetime(2026, 12, 31)
    jan1 = datetime(2027, 1, 1)
    assert weekly_period_key(dec31) == weekly_period_key(jan1) == "2026-W53"
    # 跨年后一周则换 key
    assert weekly_period_key(datetime(2027, 1, 4)) == "2027-W01"


def test_monthly_period_key():
    assert monthly_period_key(datetime(2026, 10, 19)) == "2026-10"
    assert monthly_period_key(datetime(2026, 11, 1)) == "2026-11"
    # 同月不同日同 key
    assert monthly_period_key(datetime(2026, 11, 1)) == \
        monthly_period_key(datetime(2026, 11, 28))


def test_period_key_rejects_unsupported_type():
    with pytest.raises(ValueError):
        period_key("on_demand", datetime(2026, 10, 19))
    with pytest.raises(ValueError):
        period_key("incident_driven", datetime(2026, 10, 19))


def test_last_day_of_month():
    assert _last_day_of_month(datetime(2026, 10, 19)) == 31
    assert _last_day_of_month(datetime(2026, 2, 10)) == 28
    assert _last_day_of_month(datetime(2024, 2, 10)) == 29  # 闰年
    assert _last_day_of_month(datetime(2026, 12, 5)) == 31


# ---------------------------------------------------------------------------
# 到期判定（用 db_session fixture，隔离库）
# ---------------------------------------------------------------------------

def _set_reports_config(db, key: str, value):
    """写一条 soc_system_config(category='reports', key=...) 。"""
    from app.models.system_config import SystemConfig

    row = db.query(SystemConfig).filter(
        SystemConfig.category == "reports", SystemConfig.key == key
    ).first()
    if row is None:
        row = SystemConfig(category="reports", key=key, value=str(value),
                           value_type="string")
        db.add(row)
    else:
        row.value = str(value)
    db.commit()
    return row


def test_weekly_due_on_configured_weekday(db_session):
    """默认周一 08:00 出周报。"""
    monday_9am = datetime(2026, 10, 19, 9, 0)  # 周一
    assert is_due(db_session, "weekly", monday_9am) is True


def test_weekly_not_due_on_other_weekday(db_session):
    tuesday_9am = datetime(2026, 10, 20, 9, 0)  # 周二
    assert is_due(db_session, "weekly", tuesday_9am) is False


def test_weekly_not_due_before_hour(db_session):
    """生成时刻未到不算到期。"""
    monday_7am = datetime(2026, 10, 19, 7, 0)
    assert is_due(db_session, "weekly", monday_7am) is False


def test_weekly_due_at_exact_hour(db_session):
    """整点即到期（含）。"""
    monday_8am = datetime(2026, 10, 19, 8, 0)
    assert is_due(db_session, "weekly", monday_8am) is True


def test_monthly_due_on_configured_day(db_session):
    """默认每月 1 号 08:00 出月报。"""
    assert is_due(db_session, "monthly", datetime(2026, 11, 1, 9, 0)) is True
    assert is_due(db_session, "monthly", datetime(2026, 11, 2, 9, 0)) is False


def test_monthly_day_config_overshoot_falls_back_to_last_day(db_session):
    """配置 31 号但当月只有 30 天 → 落到当月最后一天。"""
    _set_reports_config(db_session, "auto_monthly_day", 31)
    # 2026-11 只有 30 天 → 目标日 = 30
    assert is_due(db_session, "monthly", datetime(2026, 11, 30, 9, 0)) is True
    assert is_due(db_session, "monthly", datetime(2026, 11, 29, 9, 0)) is False


def test_weekly_disabled_by_config(db_session):
    """外置开关能关掉自动生成。"""
    _set_reports_config(db_session, "auto_weekly_enabled", "false")
    assert is_due(db_session, "weekly", datetime(2026, 10, 19, 9, 0)) is False


def test_monthly_disabled_by_config(db_session):
    _set_reports_config(db_session, "auto_monthly_enabled", "false")
    assert is_due(db_session, "monthly", datetime(2026, 11, 1, 9, 0)) is False


def test_weekday_override(db_session):
    """外置配置能改生成日（改成周日）。"""
    _set_reports_config(db_session, "auto_weekly_weekday", 6)  # 6=周日
    assert is_due(db_session, "weekly", datetime(2026, 10, 25, 9, 0)) is True  # 周日
    assert is_due(db_session, "weekly", datetime(2026, 10, 19, 9, 0)) is False  # 周一


def test_hour_override(db_session):
    """外置配置能改生成时刻。"""
    _set_reports_config(db_session, "auto_weekly_hour", 18)
    assert is_due(db_session, "weekly", datetime(2026, 10, 19, 9, 0)) is False
    assert is_due(db_session, "weekly", datetime(2026, 10, 19, 18, 0)) is True


def test_weekly_idempotent_same_period(db_session):
    """同周期已生成过 → 不再生成（核心幂等）。"""
    from datetime import timezone

    from app.models.security_report import SecurityReport

    monday_9am = datetime(2026, 10, 19, 9, 0)
    assert is_due(db_session, "weekly", monday_9am) is True

    # 造一份本周已生成的报告
    db_session.add(SecurityReport(
        report_type="weekly",
        period_start=monday_9am - timedelta(days=7),
        period_end=monday_9am,
        title="周报 · 7天 · 10台资产",
        summary="s", content={}, risk_highlights="", recommendations="",
        data_coverage={},
    ))
    db_session.commit()

    assert is_due(db_session, "weekly", monday_9am) is False


def test_monthly_idempotent_same_period(db_session):
    from app.models.security_report import SecurityReport

    nov_9am = datetime(2026, 11, 1, 9, 0)
    assert is_due(db_session, "monthly", nov_9am) is True

    db_session.add(SecurityReport(
        report_type="monthly",
        period_start=nov_9am - timedelta(days=30),
        period_end=nov_9am,
        title="月报 · 30天 · 10台资产",
        summary="s", content={}, risk_highlights="", recommendations="",
        data_coverage={},
    ))
    db_session.commit()

    assert is_due(db_session, "monthly", nov_9am) is False


def test_weekly_not_blocked_by_monthly_report(db_session):
    """不同类型的报告互不影响。"""
    from app.models.security_report import SecurityReport

    monday_9am = datetime(2026, 10, 19, 9, 0)
    db_session.add(SecurityReport(
        report_type="monthly",
        period_start=monday_9am - timedelta(days=30),
        period_end=monday_9am,
        title="月报",
        summary="s", content={}, risk_highlights="", recommendations="",
        data_coverage={},
    ))
    db_session.commit()
    assert is_due(db_session, "weekly", monday_9am) is True


def test_unsupported_type_not_due(db_session):
    assert is_due(db_session, "on_demand", datetime(2026, 10, 19, 9, 0)) is False
    assert is_due(db_session, "incident_driven", datetime(2026, 10, 19, 9, 0)) is False
