"""Regression tests for the AI double-allow() QPS collision (issue: 报告「AI 解读未启用」).

Root cause
----------
Several services called ``ai_budget.allow()`` as an outer guard and then called
``ai_chat(...)``, which internally calls ``ai_budget.allow()`` again. The first
call consumes the QPS slot (``_last_call_ts = now``), so the second call sees
``now - _last_call_ts ≈ 0 < MIN_INTERVAL_SECONDS`` and is rejected with
「AI 调用过于频繁（限流间隔 0.5s）」— i.e. the feature degraded to the rule
template **100% of the time**, with no user-visible reason.

The fix (matching the pattern already used by ``reconcile_ai`` since
2026-10-18) is: drop the outer ``allow()`` and let ``ai_chat`` own the rate
limiting, passing ``wait=True`` for user-initiated calls so a QPS violation
waits 0.5s and retries instead of degrading.
"""
import ast
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES = os.path.join(BACKEND, "app", "services")

# Services that must not double-count the AI rate limiter.
GUARDED_SERVICES = [
    "report_generator.py",
    "impact_analysis.py",
    "compliance_ai.py",
    "knowledge_service.py",
    "asset_security.py",
    "asset_risk.py",
    os.path.join("behavior_profile", "ai_summary.py"),
]


def _executable_ai_budget_allow_calls(path):
    """Line numbers of executable ``ai_budget.allow(...)`` calls (AST-based).

    AST is used so that mentions inside docstrings/comments are not counted —
    those are documentation, not behaviour.
    """
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    hits = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "allow"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ai_budget"
        ):
            hits.append(node.lineno)
    return hits


@pytest.mark.parametrize("rel", GUARDED_SERVICES)
def test_no_outer_budget_guard_before_ai_chat(rel):
    """No service may call ai_budget.allow() before ai_chat().

    The outer guard consumes the QPS slot, making the inner allow() inside
    ai_chat() always fail with a 0-second interval.
    """
    path = os.path.join(SERVICES, rel)
    assert os.path.exists(path), "service file missing: %s" % rel
    hits = _executable_ai_budget_allow_calls(path)
    assert not hits, (
        "%s still calls ai_budget.allow() at line(s) %s — this double-counts "
        "the rate limiter and makes ai_chat() fail every time "
        "(drop the outer guard, use ai_chat(wait=True))" % (rel, hits)
    )


@pytest.mark.parametrize("rel", GUARDED_SERVICES)
def test_ai_chat_uses_wait_true(rel):
    """User-initiated AI calls must wait out the QPS interval, not degrade."""
    path = os.path.join(SERVICES, rel)
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ai_chat"
        ):
            kw = {k.arg for k in node.keywords if k.arg}
            calls.append((node.lineno, kw))
    assert calls, "%s has no ai_chat() call" % rel
    bad = [ln for ln, kw in calls if "wait" not in kw and "_budget" not in kw]
    assert not bad, (
        "%s: ai_chat() at line(s) %s lacks wait=True — a QPS violation will "
        "degrade the feature instead of retrying" % (rel, bad)
    )


def test_report_records_ai_source_and_degrade_reason():
    """The report must record whether AI was used and, if not, why.

    Otherwise the user sees 「AI 解读未启用」 with no way to tell whether the
    cause was the rate limiter, the daily quota, the circuit breaker, or a
    malformed model response.
    """
    path = os.path.join(SERVICES, "report_generator.py")
    src = open(path, encoding="utf-8").read()
    for needle in ("ai_source", "ai_degraded", "ai_degrade_reason"):
        assert needle in src, (
            "report_generator must persist %r into data_coverage" % needle
        )


def test_double_allow_would_be_rejected():
    """Guard the guard: prove the old pattern really does get rejected.

    This documents *why* the outer allow() must not exist — if the limiter
    ever changes so that two consecutive allows both pass, this test still
    holds because it asserts the observable rejection, not the implementation.
    """
    from app.services.ai_budget import ai_budget

    # First allow consumes the slot.
    assert ai_budget.allow() is True
    # Immediately after, the second allow must be rejected (interval ~0s).
    assert ai_budget.allow() is False
    assert ai_budget.last_reject_reason, "rejection reason should be recorded"
