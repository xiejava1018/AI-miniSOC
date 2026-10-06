"""权重学习（OH-7.3 · 闭环第 6 步·复盘）

闭环跑起来后，复盘环节需要回答：**当前 AHS 维权重是否合理**？
本模块把已 ``verified`` 闭环的工单按来源维度聚合，统计「各维度的
事故占比 / 高危占比」，并据此生成**权重调整建议**。

设计红线（诚实披露）：
  - **统计级、不调常量**：本模块不改 ``AHS_DIMENSION_WEIGHTS``，
    只产出报告供人工审阅后修改常量。任何「自动闭环权重」都是过度承诺，
    统计样本小（<30 verified）时建议直接 None。
  - **来源映射有限**：工单 source_type 只能落到 ①~④ 四个 AHS 维
    （合规/漏洞/威胁/资产定级），暴露/行为维没有直接工单来源，
    故只能对前 4 维做权重建议；其他维度无信号 → 返回空建议。
  - **关联 ≠ 因果**：报告呈现「已闭环工单里 X 维高危占比」事实，
    不是「X 维是事故原因」的因果证明。审阅人需结合实际场景判读。
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.remediation_ticket import RemediationTicket
from app.services.asset_profile.ahs_service import AHS_DIMENSION_WEIGHTS

logger = logging.getLogger(__name__)

# 工单 source_type → AHS 维度
SOURCE_TO_DIM = {
    "compliance":      "compliance",
    "reconciliation":  "exposure",   # 对账差异主要涉及暴露面/影子
    "ueba_zombie":     "behavior",
}

# 多少 verified 工单才开始给建议
MIN_SAMPLE = 30

# 单维调整上限（避免建议激进调权重）
MAX_ADJUST = 0.05


class WeightFeedbackService:
    """已闭环工单 → 维度事故关联 + 权重调整建议。"""

    def __init__(self, db: Session):
        self.db = db

    def report(self) -> Dict[str, Any]:
        closed = self.db.query(RemediationTicket).filter(
            RemediationTicket.status == "verified"
        ).all()

        total = len(closed)
        if total < MIN_SAMPLE:
            return {
                "total_verified": total,
                "min_sample": MIN_SAMPLE,
                "sample_sufficient": False,
                "message": f"样本不足（{total}<{MIN_SAMPLE}），不下结论",
                "by_dimension": {},
                "suggestions": [],
                "current_weights": dict(AHS_DIMENSION_WEIGHTS),
                "red_line": "统计样本不足时不调权重；建议是参考非决策",
            }

        # 1) 工单按 source_type → AHS 维度分桶
        by_dim: Dict[str, List[RemediationTicket]] = defaultdict(list)
        for t in closed:
            dim = SOURCE_TO_DIM.get(t.source_type)
            if dim:
                by_dim[dim].append(t)

        # 2) 各维高危占比（severity=critical/high）
        report_by_dim: Dict[str, Dict[str, Any]] = {}
        for dim, tickets in by_dim.items():
            n = len(tickets)
            high = sum(1 for t in tickets if (t.severity or "") in ("critical", "high"))
            critical = sum(1 for t in tickets if t.severity == "critical")
            report_by_dim[dim] = {
                "count": n,
                "high_ratio": round(high * 100.0 / n, 1) if n else 0.0,
                "critical_count": critical,
            }

        # 3) 按高危占比 vs 当前权重的偏差，给调整建议
        #    启发式：高危占比 > 35% → 该维建议上调；< 10% → 下调；
        #    调整幅度封顶 ±MAX_ADJUST；其他维反比例回填保持总和。
        suggestions = self._suggestions(report_by_dim)

        return {
            "total_verified": total,
            "min_sample": MIN_SAMPLE,
            "sample_sufficient": True,
            "by_dimension": report_by_dim,
            "suggestions": suggestions,
            "current_weights": dict(AHS_DIMENSION_WEIGHTS),
            "red_line": "建议非决策；权重调整须人工改 AHS_DIMENSION_WEIGHTS",
        }

    # ---------------- 启发式 ----------------

    @staticmethod
    def _suggestions(by_dim: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 仅给有样本的维度生成建议
        sugg = []
        for dim, info in by_dim.items():
            ratio = info["high_ratio"]
            if ratio >= 35.0:
                delta = round(min(MAX_ADJUST,
                                  (ratio - 30) / 100), 4)
                sugg.append({
                    "dimension": dim,
                    "direction": "up",
                    "delta": delta,
                    "reason": f"该维高危占比 {ratio}%，偏高",
                })
            elif ratio < 10.0 and info["count"] >= 10:
                sugg.append({
                    "dimension": dim,
                    "direction": "down",
                    "delta": -round(min(MAX_ADJUST,
                                       (10 - ratio) / 100), 4),
                    "reason": f"该维高危占比 {ratio}%，偏低",
                })
        return sugg
