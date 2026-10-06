"""外侧复测通路（OH-7.2 · S12 Phase 1）

整改工单 resolved 后，闭环的下一步是**从系统外侧再测一遍**——处理人说
修好了不算数，平台独立复测仍暴露问题就自动重开。本模块是复测通路，
复用既有扫描能力，不重写：

  - 触发复测：建一条 ``ScannerTask``（mode=ports/internal，扫描器轮询
    认领），与 POST /scan/run 同款契约。
  - 结果回取：扫完后 ScannerTask.status=success，对照 ``ScanFinding``
    （暴露面）与 ``AssetVulnerability``（漏洞）评估。
  - 判定：纯函数比对，给 pass/fail/inconclusive + evidence。

「外侧」语义（诚实披露边界）：
  - 当前复测以**内部扫描器从网络侧重测**（端口可达性/服务指纹/漏洞关联），
    这是比处理人自证更强的独立证据，但**不是真正的互联网外部视角**
    （无外部 VPS/黑盒扫描器）。措辞统一「网络侧独立复测」，不冒充
    「外部攻击者视角」。
  - 扫描器未跑/任务仍 pending/running → inconclusive，**不判 pass**
    （缺证据 ≠ 达标，与 compliance unknown 同红线）。
  - 复测通路本身不自动改工单状态；自动 reopen 的编排见 verification_loop
    （OH-4.11）。本模块提供判定，落决策权在调用方，便于人工审阅。
"""
from __future__ import annotations

import logging
import uuid as uuidlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.remediation_ticket import RemediationTicket
from app.models.asset import Asset
from app.models.scanner_models import ScannerTask, ScanFinding
from app.models.vulnerability import AssetVulnerability

logger = logging.getLogger(__name__)

# 复测模式
MODE_PORTS = "ports"        # 端口/服务可达性（暴露面类整改）
MODE_INTERNAL = "internal"  # 主机存活（僵尸/影子类整改）

# 结论
PASS = "pass"
FAIL = "fail"
INCONCLUSIVE = "inconclusive"


class ExternalVerifier:
    """网络侧独立复测通路。"""

    def __init__(self, db: Session):
        self.db = db

    # ---------------- 触发 ----------------

    def trigger_retest(
        self,
        ticket_id: Any,
        *,
        username: str,
        mode: str = MODE_PORTS,
    ) -> Dict[str, Any]:
        ticket = self.db.get(RemediationTicket, ticket_id)
        if ticket is None:
            raise LookupError("工单不存在")
        if mode not in (MODE_PORTS, MODE_INTERNAL):
            raise ValueError("mode 须为 ports/internal")

        ip = self._target_ip(ticket)
        if not ip:
            raise ValueError("工单未锚定可复测资产（无 IP）")

        task = ScannerTask(
            task_uuid=uuidlib.uuid4(),
            mode=mode,
            scope="manual",
            status="pending",
            triggered_by=username,
            target_summary=[{"type": "ip", "value": ip}],
            assign_mode="auto",
            capabilities=[mode],
            nmap_args=None,
            run_reason="retest",
        )
        # 溯源：把工单 id 记到 parent_task_id 不合适（那是任务链）；
        # 用 run_reason=retest + 待评估时按 IP+时间窗回查。
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        return {
            "ticket_id": str(ticket.id),
            "task_uuid": str(task.task_uuid),
            "target_ip": ip,
            "mode": mode,
            "status": task.status,
            "note": "复测任务已建，扫描器下次轮询认领",
        }

    # ---------------- 评估 ----------------

    def evaluate_retest(self, ticket_id: Any) -> Dict[str, Any]:
        ticket = self.db.get(RemediationTicket, ticket_id)
        if ticket is None:
            raise LookupError("工单不存在")

        ip = self._target_ip(ticket)
        task = self._latest_retest_task(ip)
        if task is None:
            return self._result(ticket, ip, INCONCLUSIVE,
                                "未找到复测任务——先 trigger_retest", None)

        if task.status not in ("success", "failed"):
            return self._result(
                ticket, ip, INCONCLUSIVE,
                f"复测任务 {task.status}，尚无结论（缺证据不判达标）",
                task,
            )

        # 任务 failed = 扫描器本身没跑成，不是被测资产问题 → 仍 inconclusive
        if task.status == "failed":
            return self._result(ticket, ip, INCONCLUSIVE,
                                "复测扫描执行失败，请重派", task)

        # success：依据复测类型比对
        if task.mode == MODE_INTERNAL:
            verdict, why = self._evaluate_internal(ip, task)
        else:
            verdict, why = self._evaluate_ports(ticket, ip, task)
        return self._result(ticket, ip, verdict, why, task)

    # ---------------- 判定细则 ----------------

    def _evaluate_internal(self, ip: str, task: ScannerTask):
        """主机存活类：复测仍发现该 IP 活动 → 僵尸/影子未清 = fail。"""
        found = self._findings_after(task, ip)
        if found:
            return FAIL, f"复测仍发现主机存活（{len(found)} 条发现）"
        return PASS, "复测未再发现该主机活动"

    def _evaluate_ports(self, ticket: RemediationTicket, ip: str,
                        task: ScannerTask):
        """端口/漏洞类：复测后仍有 open 高危端口/漏洞关联 = fail。

        降级诚实披露：无法从工单自动得知「具体哪个端口/漏洞是整改目标」
        （description 自由文本），故采用保守口径——复测发现任何
        高危端口暴露或 OPEN 漏洞关联即判 fail。这可能偏严（暴露了
        整改目标之外的问题），在 message 中明示。
        """
        found = self._findings_after(task, ip)
        # ScanFinding 本身不区分端口风险；用漏洞关联作硬证据
        open_vulns = self._open_vulns_after(ticket, task)
        if open_vulns:
            return FAIL, (
                f"复测后该资产仍有 {len(open_vulns)} 个 OPEN 漏洞关联"
                "（保守口径：任一未闭合即判未通过）"
            )
        if found:
            return INCONCLUSIVE, (
                f"复测有 {len(found)} 条网络发现但无 OPEN 漏洞硬证据；"
                "具体整改目标需人工核对（端口明细未结构化回传）"
            )
        return PASS, "复测未发现 OPEN 漏洞关联或网络暴露"

    # ---------------- 辅助 ----------------

    def _target_ip(self, ticket: RemediationTicket) -> Optional[str]:
        """从工单锚定资产取 IP：优先 ticket.asset_id，回退来源回查。"""
        if ticket.asset_id is not None:
            a = self.db.get(Asset, ticket.asset_id)
            if a is not None:
                return a.asset_ip
        return self._ip_from_source(ticket)

    def _ip_from_source(self, ticket: RemediationTicket) -> Optional[str]:
        from app.models.asset_reconciliation import AssetReconciliation
        from app.models.compliance import ComplianceFinding

        # reconciliation → asset（shadow 可能 asset_id 为空，
        # IP 落在 details JSON；结构见 asset_reconciliation._details_*）
        if ticket.reconciliation_id is not None:
            rec = self.db.get(AssetReconciliation,
                              ticket.reconciliation_id)
            if rec is not None:
                if rec.asset_id is not None:
                    a = self.db.get(Asset, rec.asset_id)
                    if a is not None:
                        return a.asset_ip
                ip = self._ip_from_details(rec.details)
                if ip:
                    return ip

        # compliance → asset
        if ticket.compliance_finding_id is not None:
            cf = self.db.get(ComplianceFinding,
                             ticket.compliance_finding_id)
            if cf is not None:
                a = self.db.get(Asset, cf.asset_id)
                if a is not None:
                    return a.asset_ip
        return None

    def _ip_from_details(self, details: Any) -> Optional[str]:
        """从对账 details JSON 提取 IP（兼容常见键，不承诺结构统一）。"""
        if not isinstance(details, dict):
            return None
        for key in ("asset_ip", "ip", "detected_ip", "observed_ip"):
            v = details.get(key)
            if isinstance(v, str) and v:
                return v
        return None

    def _latest_retest_task(self, ip: Optional[str]) -> Optional[ScannerTask]:
        if not ip:
            return None
        return self.db.execute(
            select(ScannerTask)
            .where(ScannerTask.run_reason == "retest")
            .order_by(ScannerTask.id.desc())
            .limit(1)
        ).scalar()

    def _findings_after(self, task: ScannerTask, ip: str) -> List[ScanFinding]:
        # ScanFinding 软关联 task_uuid；同 IP 且时间晚于任务创建
        return list(self.db.execute(
            select(ScanFinding)
            .where(ScanFinding.scan_task_uuid == task.task_uuid,
                   ScanFinding.asset_ip == ip)
        ).scalars())

    def _open_vulns_after(self, ticket: RemediationTicket,
                          task: ScannerTask) -> List[AssetVulnerability]:
        """该资产当前仍 OPEN 的漏洞关联。"""
        from app.models.compliance import ComplianceFinding

        asset_id = ticket.asset_id
        if asset_id is None and ticket.compliance_finding_id is not None:
            cf = self.db.get(ComplianceFinding,
                             ticket.compliance_finding_id)
            asset_id = cf.asset_id if cf else None
        if asset_id is None:
            return []
        return list(self.db.execute(
            select(AssetVulnerability)
            .where(AssetVulnerability.asset_id == asset_id,
                   AssetVulnerability.status == "open")
        ).scalars())

    def _result(self, ticket, ip, verdict, message, task):
        return {
            "ticket_id": str(ticket.id),
            "target_ip": ip,
            "verdict": verdict,
            "message": message,
            "task_uuid": str(task.task_uuid) if task else None,
            "task_status": task.status if task else None,
            "red_line": "网络侧独立复测（非互联网外部视角）；缺证据不判达标",
        }
