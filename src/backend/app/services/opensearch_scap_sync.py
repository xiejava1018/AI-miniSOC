"""
OpenSearch SCAP（CVE）漏洞数据同步服务（T5，2026-08-15）

背景（POC-1 结论，docs/design/2026-08-15-脆弱性管理-点亮与闭环设计实施计划.md §11.3）：
- 原 Wazuh API `/vulnerability` 路由在本环境全部 404，`wazuh_client.get_vulnerabilities`
  真实模式不可用 → 本服务接管 SCAP 真实数据源；
- 数据实际躺在 OpenSearch `wazuh-states-vulnerabilities-*`（实测 8.1 万+ 文档、18 agent、
  detected_at 持续更新至最新），复用 alert_query.py 的 httpx OpenSearch 客户端范式。

字段映射（实测 ECS 顶层结构，无 data. 前缀；与 POC-1 记录的 wazuh-alerts 的
data.vulnerability.* 结构不同，两者均为真实结构）：
  vulnerability.id          → cve_id
  vulnerability.description → description / title 兜底（states 索引无 title 字段）
  vulnerability.severity    → severity（Critical/High/Medium/Low；'-' 跳过）
  vulnerability.score       → cvss_score（嵌套 {"base": 5.9, "version": "3.1"}，取 base 真值）
  vulnerability.reference   → references（单数字符串逗号分隔 → 列表；注意不是复数 references）
  vulnerability.published_at→ published_date
  vulnerability.detected_at → AssetVulnerability.detected_at（文档检出时间，非同步时刻 §14.5-3）
  package.name/version/architecture → affected_packages
  agent.id                  → Asset.wazuh_agent_id 关联键

重新检出语义（§14.5-2）：
- 关联存在且 status='fixed' → 复活为 open，刷新 detected_at，清空 fixed_at
- 关联存在且 open → 刷新 detected_at
- 关联不存在 → 新建 open

mock 分支：use_mock=True 时使用 mock_scap_data.MockSCAPDataGenerator（T0 同款），
结构与 wazuh_scap_sync._create_vulnerability_from_wazuh 兼容。
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_retry import RetryConfig, RetryStats, http_retry
from app.models.vulnerability import Vulnerability, AssetVulnerability
from app.models.asset import Asset
from app.schemas.vulnerability import SeverityEnum, ScannerEnum, VulnerabilityStatusEnum
from app.services.opensearch.os_field_map import (
    OSFieldProbe,
    extract_vuln_fields,
)

logger = logging.getLogger(__name__)

# states 索引（当前累积状态）；wazuh-alerts-4.x-* 漏洞告警可作 P5 增补源
VULN_INDEX = "wazuh-states-vulnerabilities-*"


class OpenSearchSCAPSyncService:
    """从 OpenSearch 拉取 Wazuh 漏洞状态并落库的 SCAP 同步服务"""

    SEVERITY_MAPPING = {
        "Critical": SeverityEnum.CRITICAL,
        "High": SeverityEnum.HIGH,
        "Medium": SeverityEnum.MEDIUM,
        "Low": SeverityEnum.LOW,
    }

    def __init__(self):
        self._os = httpx.Client(
            base_url=settings.OPENSEARCH_URL.rstrip("/"),
            auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            verify=False,  # Wazuh/OpenSearch 自签名证书
            timeout=30.0,
        )
        # P3-T1：重试统计与装饰器
        self._retry_stats = RetryStats()

    @http_retry(config=RetryConfig.default(), stats=RetryStats())
    def _send_search(self, url, json):
        """P3-T1：单次 _search POST，5xx/超时重试。"""
        return self._os.post(url, json=json)

    def close(self):
        self._os.close()

    # ------------------------------------------------------------------
    # OpenSearch 查询
    # ------------------------------------------------------------------

    def _search(self, body: dict) -> List[dict]:
        """执行 _search 并返回 hits 列表（异常向上抛，由调用方统计 errors，P3-T1 重试）"""
        resp = self._send_search(f"/{VULN_INDEX}/_search", body)
        resp.raise_for_status()
        return resp.json().get("hits", {}).get("hits", [])

    def _fetch_vulnerability_docs(
        self, limit: int = 1000, agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        拉取漏洞文档（按 detected_at 倒序），内存按
        (agent.id, vulnerability.id, package.name+version) 去重保留最新。
        过滤：无 CVE 编号 / severity='-'（无严重度）/ under_evaluation=True 的文档。
        """
        must: List[dict] = [{"exists": {"field": "vulnerability.id"}}]
        if agent_id:
            must.append({"term": {"agent.id": agent_id}})

        body = {
            "size": max(limit * 2, 200),  # 多拉一倍给去重留余量（单页 ≤ 10000）
            "query": {
                "bool": {
                    "filter": must,
                    "must_not": [
                        {"term": {"vulnerability.severity": "-"}},
                        {"term": {"vulnerability.under_evaluation": True}},
                    ],
                }
            },
            "sort": [{"vulnerability.detected_at": {"order": "desc", "unmapped_type": "date"}}],
            "_source": [
                "agent.id", "agent.name",
                "vulnerability.id", "vulnerability.description", "vulnerability.severity",
                "vulnerability.score", "vulnerability.reference", "vulnerability.published_at",
                "vulnerability.detected_at", "vulnerability.classification",
                "package.name", "package.version", "package.architecture", "package.condition",
            ],
        }
        body["size"] = min(body["size"], 10000)

        hits = self._search(body)

        # 内存去重：同 (agent, cve, package) 只保留 detected_at 最新一条
        dedup: Dict[str, dict] = {}
        for h in hits:
            src = h.get("_source") or {}
            v = src.get("vulnerability") or {}
            agent = src.get("agent") or {}
            pkg = src.get("package") or {}
            cve = (v.get("id") or "").strip()
            if not cve:
                continue
            key = f"{agent.get('id')}|{cve}|{pkg.get('name')}|{pkg.get('version')}"
            prev = dedup.get(key)
            if prev is None or self._detected_at_of(src) >= self._detected_at_of(prev):
                dedup[key] = src

        docs = list(dedup.values())[:limit]
        logger.info(
            "OpenSearch SCAP fetch: hits=%d dedup=%d returned=%d (agent_id=%s)",
            len(hits), len(dedup), len(docs), agent_id or "ALL",
        )
        return docs

    @staticmethod
    def _detected_at_of(src: dict) -> str:
        return str(((src.get("vulnerability") or {}).get("detected_at")) or "")

    # ------------------------------------------------------------------
    # 字段解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value) -> Optional[datetime]:
        """ISO8601 → datetime（失败返回 None）"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_cvss(score_field) -> Optional[float]:
        """
        解析嵌套 CVSS：实测结构 {"base": 5.9, "version": "3.1"}；
        兼容 {"base_score": x} / 纯数字。解析失败返回 None（不用 severity 硬映射）。
        """
        if score_field is None:
            return None
        if isinstance(score_field, (int, float)):
            return float(score_field)
        if isinstance(score_field, dict):
            for k in ("base", "base_score", "score", "value"):
                if k in score_field and isinstance(score_field[k], (int, float)):
                    v = float(score_field[k])
                    if 0.0 <= v <= 10.0:
                        return v
        return None

    @staticmethod
    def _parse_reference(ref_field) -> Optional[List[str]]:
        """reference 为单数字符串（逗号分隔 URL）→ 列表（§9.1 修正：不是复数 references）"""
        if not ref_field:
            return None
        if isinstance(ref_field, list):
            return [str(r) for r in ref_field if r] or None
        if isinstance(ref_field, str):
            items = [u.strip() for u in ref_field.split(",") if u.strip()]
            return items or None
        return None

    def _vuln_from_doc(self, src: dict) -> Optional[Vulnerability]:
        """OpenSearch 文档 → Vulnerability ORM 对象（不含 has_exploit，由 KEV 服务富化）

        P2-T1：改走统一映射层（os_field_map）。禁止 data.vulnerability.* / 顶层混写。
        """
        # P2-T1：走统一字段映射层
        fields = extract_vuln_fields(src, source="states")
        # 关键字段缺失探针
        missing = self._field_probe.check(fields)
        if missing:
            logger.warning("OS 漏洞文档缺关键字段 %s，丢弃: %s", missing, (fields.cve_id or "<no cve>"))
            return None

        # severity 合法值校验
        severity = self.SEVERITY_MAPPING.get(fields.severity) if fields.severity else None
        if severity is None:
            return None

        cve = fields.cve_id
        description = fields.description or ""
        title = description[:200] if description else cve
        published = self._parse_datetime(fields.published_at)

        affected = fields.package

        return Vulnerability(
            type="scap",
            cve_id=cve,
            title=title,
            description=description or None,
            cvss_score=fields.cvss_score,
            cvss_vector=None,  # states 索引无独立向量字段
            severity=severity,
            affected_packages=affected,
            fix_suggestion=None,  # states 索引无 fix 版本
            references=fields.references,
            published_date=published.date() if published else None,
            has_exploit=False,  # 由 CISA KEV 富化（T6）
            discovered_at=self._parse_datetime(fields.detected_at) or datetime.utcnow(),
        )

    _field_probe = OSFieldProbe()  # 复用探针实例

    # ------------------------------------------------------------------
    # 同步主流程
    # ------------------------------------------------------------------

    @classmethod
    def sync_all_vulnerabilities(
        cls,
        db: Session,
        limit: int = 1000,
        use_mock: bool = False,
        agent_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        同步 SCAP 漏洞数据（真实=OpenSearch states 索引；mock=MockSCAPDataGenerator）。

        Returns:
            与旧 wazuh_scap_sync 兼容的统计结构
        """
        if use_mock:
            return cls._sync_mock(db, agent_id=agent_id)

        stats = {
            "total_agents": 0,
            "processed_agents": 0,
            "new_vulnerabilities": 0,
            "new_associations": 0,
            "revived_associations": 0,
            "updated_associations": 0,
            "skipped_no_asset": 0,
            "errors": 0,
        }

        svc = cls()
        try:
            docs = svc._fetch_vulnerability_docs(limit=limit, agent_id=agent_id)
            agents_seen = set()

            # ---------- 阶段 A：预载缓存（asset/vuln 全表小，避免逐 doc 查询往返） ----------
            asset_cache = {}   # agent_id -> Asset
            for a in db.query(Asset).filter(Asset.wazuh_agent_id.isnot(None)).all():
                asset_cache[str(a.wazuh_agent_id)] = a
            name_cache = {a.name: a for a in db.query(Asset).filter(Asset.name.isnot(None)).all()}
            vuln_cache = {v.cve_id: v for v in db.query(Vulnerability).all()}

            pending_assocs = []  # [(asset, vuln_obj_or_cache, detected_at)]
            for src in docs:
                agent = src.get("agent") or {}
                aid, aname = agent.get("id"), agent.get("name") or agent.get("id")
                if aid:
                    agents_seen.add(aid)

                # 资产匹配（agent_id 优先，name 兜底；找不到跳过不创建）
                asset = asset_cache.get(str(aid)) if aid else None
                if not asset and aname and aname in name_cache:
                    asset = name_cache[aname]
                    if aid:
                        asset.wazuh_agent_id = str(aid)
                        asset_cache[str(aid)] = asset
                if not asset:
                    stats["skipped_no_asset"] += 1
                    continue

                # 漏洞定义 upsert
                vuln_obj = svc._vuln_from_doc(src)
                if vuln_obj is None:
                    stats["skipped_no_asset"] += 1
                    continue
                cve = vuln_obj.cve_id
                existing_vuln = vuln_cache.get(cve)
                if existing_vuln is None:
                    db.add(vuln_obj)
                    vuln_cache[cve] = vuln_obj
                    stats["new_vulnerabilities"] += 1
                else:
                    for field in ("title", "description", "cvss_score", "severity",
                                  "affected_packages", "references", "published_date", "discovered_at"):
                        new_val = getattr(vuln_obj, field)
                        if new_val is not None and getattr(existing_vuln, field) != new_val:
                            setattr(existing_vuln, field, new_val)

                pending_assocs.append((asset, vuln_cache[cve], vuln_obj.discovered_at))

            # 一次 flush：SQLAlchemy 2.0 insertmanyvalues 批量 RETURNING 填 id，避免逐条往返
            db.flush()

            # ---------- 阶段 B：关联 upsert（重新检出语义 §14.5-2） ----------
            involved_vuln_ids = {v.id for _, v, _ in pending_assocs}
            assoc_cache = {}
            if involved_vuln_ids:
                rows = db.query(AssetVulnerability).filter(
                    AssetVulnerability.scanner == ScannerEnum.WAZUH,
                    AssetVulnerability.vulnerability_id.in_(involved_vuln_ids),
                ).all()
                for r in rows:
                    assoc_cache[(str(r.asset_id), str(r.vulnerability_id))] = r

            for asset, vuln, detected_at in pending_assocs:
                try:
                    key = (str(asset.id), str(vuln.id))
                    association = assoc_cache.get(key)
                    detected_at = detected_at or datetime.utcnow()

                    if not association:
                        new_assoc = AssetVulnerability(
                            asset_id=asset.id,
                            vulnerability_id=vuln.id,
                            scanner=ScannerEnum.WAZUH,
                            status=VulnerabilityStatusEnum.OPEN,
                            detected_at=detected_at,
                            due_date=AssetVulnerability.compute_due_date(vuln.severity, detected_at),
                        )
                        db.add(new_assoc)
                        assoc_cache[key] = new_assoc
                        stats["new_associations"] += 1
                    elif association.status == VulnerabilityStatusEnum.FIXED:
                        # 修复后再次检出 → 复活（并按严重度重设修复时限）
                        association.status = VulnerabilityStatusEnum.OPEN
                        association.detected_at = detected_at
                        association.fixed_at = None
                        association.due_date = AssetVulnerability.compute_due_date(vuln.severity, detected_at)
                        stats["revived_associations"] += 1
                    else:
                        association.detected_at = detected_at
                        stats["updated_associations"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("SCAP assoc failed asset=%s vuln=%s: %s", asset.id, vuln.cve_id, e)

            stats["total_agents"] = len(agents_seen)
            stats["processed_agents"] = len(agents_seen)
            db.commit()
            logger.info("OpenSearch SCAP sync completed: %s", stats)
        except Exception as e:
            db.rollback()
            logger.error("OpenSearch SCAP sync failed: %s", e)
            raise
        finally:
            svc.close()

        return stats

    @classmethod
    def sync_agent_vulnerabilities(
        cls, db: Session, agent_id: str, agent_name: str = None, limit: int = 500
    ) -> Dict[str, int]:
        """同步单个 agent 的 SCAP 数据（供 POST /sync/wazuh/agents/{agent_id}）"""
        stats = cls.sync_all_vulnerabilities(db, limit=limit, agent_id=agent_id)
        # 单 agent 视角的 total/processed 语义
        if stats.get("total_agents"):
            stats["processed_agents"] = 1
        return stats

    def _process_doc(self, db: Session, src: dict, agent_id, agent_name) -> str:
        """处理单条文档，返回 new/new_association/revived/updated/skipped_no_asset"""
        # 1. 资产匹配（与旧服务一致：agent_id 优先，name 兜底；找不到跳过不创建）
        asset = None
        if agent_id:
            asset = db.query(Asset).filter(Asset.wazuh_agent_id == str(agent_id)).first()
        if not asset and agent_name:
            asset = db.query(Asset).filter(Asset.name == agent_name).first()
            if asset and agent_id:
                asset.wazuh_agent_id = str(agent_id)
                db.flush()
        if not asset:
            return "skipped_no_asset"

        # 2. 漏洞定义 upsert
        vuln_obj = self._vuln_from_doc(src)
        if vuln_obj is None:
            return "skipped_no_asset"

        vulnerability = db.query(Vulnerability).filter(
            Vulnerability.cve_id == vuln_obj.cve_id
        ).first()

        is_new_vuln = False
        if not vulnerability:
            db.add(vuln_obj)
            db.flush()
            vulnerability = vuln_obj
            is_new_vuln = True
        else:
            # 定义已存在：刷新最新字段（真实 CVSS / severity / references 等）
            changed = False
            for field in ("title", "description", "cvss_score", "severity",
                          "affected_packages", "references", "published_date", "discovered_at"):
                new_val = getattr(vuln_obj, field)
                if new_val is not None and getattr(vulnerability, field) != new_val:
                    setattr(vulnerability, field, new_val)
                    changed = True
            if changed:
                db.flush()

        # 3. 资产-漏洞关联 upsert（重新检出语义 §14.5-2）
        association = db.query(AssetVulnerability).filter(
            AssetVulnerability.asset_id == asset.id,
            AssetVulnerability.vulnerability_id == vulnerability.id,
            AssetVulnerability.scanner == ScannerEnum.WAZUH,
        ).first()

        detected_at = vuln_obj.discovered_at or datetime.utcnow()

        if not association:
            db.add(AssetVulnerability(
                asset_id=asset.id,
                vulnerability_id=vulnerability.id,
                scanner=ScannerEnum.WAZUH,
                status=VulnerabilityStatusEnum.OPEN,
                detected_at=detected_at,
            ))
            db.flush()
            return "new" if is_new_vuln else "new_association"

        if association.status == VulnerabilityStatusEnum.FIXED:
            # 修复后再次检出 → 复活
            association.status = VulnerabilityStatusEnum.OPEN
            association.detected_at = detected_at
            association.fixed_at = None
            db.flush()
            return "revived"

        association.detected_at = detected_at
        db.flush()
        return "updated"

    # ------------------------------------------------------------------
    # mock 分支（T0 同款数据源）
    # ------------------------------------------------------------------

    @classmethod
    def _sync_mock(cls, db: Session, agent_id: Optional[str] = None) -> Dict[str, int]:
        from app.services.mock_scap_data import MockSCAPDataGenerator
        from app.services.wazuh_scap_sync import WazuhSCAPSyncService  # 复用其 mock 兼容的落库逻辑

        stats = {
            "total_agents": 0, "processed_agents": 0,
            "new_vulnerabilities": 0, "new_associations": 0,
            "revived_associations": 0, "updated_associations": 0,
            "skipped_no_asset": 0, "errors": 0,
        }
        agents = MockSCAPDataGenerator.get_all_agents()
        if agent_id:
            agents = [a for a in agents if a.get("id") == agent_id]
        stats["total_agents"] = len(agents)

        for agent in agents:
            aid, aname = agent.get("id"), agent.get("name")
            vulns = MockSCAPDataGenerator.generate_agent_vulnerabilities(aid)
            stats["processed_agents"] += 1
            for vuln_data in vulns:
                try:
                    asset = WazuhSCAPSyncService._get_or_create_asset(db, aid, aname)
                    if not asset:
                        stats["skipped_no_asset"] += 1
                        continue
                    result = WazuhSCAPSyncService._process_vulnerability(
                        db, vuln_data=vuln_data, asset=asset
                    )
                    if result == "new":
                        stats["new_vulnerabilities"] += 1
                        stats["new_associations"] += 1
                    elif result == "new_association":
                        stats["new_associations"] += 1
                    elif result in ("skipped", "skipped_no_asset"):
                        stats["skipped_no_asset"] += 1
                    else:
                        stats["updated_associations"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("mock SCAP sync error agent=%s: %s", aid, e)
        db.commit()
        return stats
