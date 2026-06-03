"""
资产概览聚合服务

为资产管理下"资产概览"页提供一次性聚合接口。
设计要点:
- 1 次方法调用产出前端 4 个 KPI + 3 张分布 + 1 张趋势 + 2 张 Top 表所需的全部数据
- 任何一步失败都不影响整体返回,失败字段降级为 0 / 空
- 评分公式和高危资产定义见 docs/design/2026-06-03-asset-overview-design.md §3 D6/D7
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timezone, timedelta

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_incident import AssetIncident
from app.models.incident import Incident
from app.services.alert_query import AlertQueryService

logger = logging.getLogger(__name__)


# 复用以避免循环引用 - 来自 asset_summary.py
HIGH_RISK_PORT_NUMBERS = {
    22, 23, 21,  # SSH/Telnet/FTP
    139, 445,    # SMB/NetBIOS
    3389,        # RDP
    3306, 1433, 5432, 27017, 6379,  # 数据库
    2375,        # Docker API
    9200, 5601,  # ES/Kibana
}


def _is_high_risk_port(port_number: int) -> bool:
    return port_number in HIGH_RISK_PORT_NUMBERS


class AssetOverviewService:
    """
    资产概览聚合服务

    单次调用 build_overview() 返回:
    - kpi: 4 个总览数字
    - distribution: 3 张环图(类型/状态/重要度)
    - alert_trend_24h: 24h 告警趋势(1h 桶)
    - top_risky_assets: 评分前 10 高危资产
    - top_alert_assets: 告警数前 10 资产

    失败降级原则: 每个私有方法独立 try/except,失败时 warn log,
    整页仍能渲染(失败字段返回 0/空)
    """

    # 评分公式权重(见设计文档 D7)
    SCORE_WEIGHT_CRITICAL_CORE = 100        # criticality='core'
    SCORE_WEIGHT_OPEN_INCIDENT = 30         # 每个未关闭事件
    SCORE_WEIGHT_HIGH_RISK_PORT = 20        # 每个高危端口
    SCORE_WEIGHT_MANY_OPEN_PORTS = 10       # open_ports >= 5 加成
    SCORE_WEIGHT_OPEN_PORT_THRESHOLD = 5    # 多少个开放端口开始加成
    SCORE_WEIGHT_ALERT = 1                  # 每个 24h 告警

    # 高危资产定义(D6 5 条件命中任一)
    HIGH_RISK_ALERT_THRESHOLD = 10          # alert_24h >= 10 算高危

    def __init__(self, db: Session):
        self.db = db

    def build_overview(self) -> Dict[str, Any]:
        """
        构建资产概览完整数据

        任何子步骤失败,只影响该字段,其他字段正常返回。
        """
        kpi = self._build_kpi()
        distribution = self._build_distribution()
        alert_trend_24h = self._build_alert_trend()
        top_risky_assets = self._build_top_risky_assets()
        top_alert_assets = self._build_top_alert_assets()

        return {
            "kpi": kpi,
            "distribution": distribution,
            "alert_trend_24h": alert_trend_24h,
            "top_risky_assets": top_risky_assets,
            "top_alert_assets": top_alert_assets,
        }

    # ---------- 1. KPI ----------

    def _build_kpi(self) -> Dict[str, int]:
        """
        4 个核心数字:
        - total_assets: 资产总数
        - high_risk_assets: 高危资产数(走评分扫描后过滤)
        - alerts_24h: 24h 总告警数
        - open_incidents: 未关闭事件数
        """
        total_assets = self._safe_count(Asset, label="total_assets")
        open_incidents = self._count_open_incidents()
        alerts_24h = self._count_alerts_24h()

        # 高危资产:依赖评分扫描结果
        try:
            top_risky = self._build_top_risky_assets()
            high_risk_assets = len(top_risky)
        except Exception as e:
            logger.warning(f"高危资产统计失败,降级为 0: {e}")
            high_risk_assets = 0

        return {
            "total_assets": total_assets,
            "high_risk_assets": high_risk_assets,
            "alerts_24h": alerts_24h,
            "open_incidents": open_incidents,
        }

    def _safe_count(self, model, label: str) -> int:
        try:
            return self.db.query(func.count(model.id)).scalar() or 0
        except Exception as e:
            logger.warning(f"统计 {label} 失败,降级为 0: {e}")
            return 0

    def _count_open_incidents(self) -> int:
        try:
            return (
                self.db.query(func.count(Incident.id))
                .filter(Incident.status.in_(["open", "in_progress", "resolved"]))
                .scalar()
            ) or 0
        except Exception as e:
            logger.warning(f"统计未关闭事件失败: {e}")
            return 0

    def _count_alerts_24h(self) -> int:
        """24h 告警总数(走 AlertQueryService,失败兜底 0)"""
        try:
            alert_service = AlertQueryService(self.db)
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=24)
            stats = alert_service.get_alert_statistics(
                start_time=start_time,
                end_time=end_time
            )
            by_level = stats.get("by_level", []) or []
            return sum(int(b.get("doc_count", 0)) for b in by_level)
        except Exception as e:
            logger.warning(f"统计 24h 告警失败: {e}")
            return 0

    # ---------- 2. Distribution ----------

    def _build_distribution(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        3 张分布图数据:by_type / by_status / by_criticality
        统一格式:[{"key": "...", "count": N}, ...]
        """
        return {
            "by_type": self._group_count(Asset.asset_type, "asset_type"),
            "by_status": self._group_count(Asset.asset_status, "asset_status"),
            "by_criticality": self._group_count(Asset.criticality, "criticality"),
        }

    def _group_count(self, column, label: str) -> List[Dict[str, Any]]:
        """通用 GROUP BY count 包装器,失败兜底返回 []"""
        try:
            rows = (
                self.db.query(column.label("key"), func.count(Asset.id).label("count"))
                .group_by(column)
                .all()
            )
            return [
                {"key": (row.key or "unknown"), "count": int(row.count)}
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"分组统计 {label} 失败: {e}")
            return []

    # ---------- 3. Alert Trend ----------

    def _build_alert_trend(self) -> List[Dict[str, Any]]:
        """
        24h 告警趋势(1h 桶)

        走 AlertQueryService.get_alert_trend(),Phase 2 接 OpenSearch date_histogram。
        当前是 mock,返回 24 个点。
        """
        try:
            alert_service = AlertQueryService(self.db)
            return alert_service.get_alert_trend(hours=24, interval_hours=1)
        except Exception as e:
            logger.warning(f"24h 告警趋势获取失败,返回空趋势: {e}")
            return []

    # ---------- 4. Top Risky Assets (D6/D7) ----------

    def _build_top_risky_assets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        评分前 N 的高危资产

        评分公式(D7):
        - criticality='core' → +100
        - open_incidents(该资产) × 30
        - high_risk_ports(该资产) × 20
        - open_ports >= 5 → +10
        - alert_24h(该资产) × 1

        排序后取前 N,资产 ID 用于前端跳转详情页。
        """
        try:
            # 一次拉所有资产,在内存里计算
            assets = self.db.query(Asset).all()
            if not assets:
                return []

            # 预聚合每个资产的 port/incident/alert 计数
            asset_ids = [a.id for a in assets]
            asset_ips = [a.asset_ip for a in assets if a.asset_ip]

            # 每个资产的开放端口数 + 高危端口数
            port_stats = self._aggregate_port_stats(asset_ids)
            # 每个资产的未关闭事件数
            incident_stats = self._aggregate_incident_stats(asset_ids)
            # 每个资产的 24h 告警数(IP 维度)
            alert_stats = self._aggregate_alert_stats(asset_ips)

            scored: List[Dict[str, Any]] = []
            for asset in assets:
                try:
                    factors: List[str] = []
                    score = 0

                    # criticality 权重
                    if asset.criticality == "core":
                        score += self.SCORE_WEIGHT_CRITICAL_CORE
                        factors.append("core 资产")

                    # 端口相关
                    p_stat = port_stats.get(str(asset.id), {"open": 0, "high_risk": 0})
                    open_ports = p_stat["open"]
                    high_risk_ports = p_stat["high_risk"]
                    score += high_risk_ports * self.SCORE_WEIGHT_HIGH_RISK_PORT
                    if high_risk_ports > 0:
                        factors.append(f"高危端口 {high_risk_ports}")
                    if open_ports >= self.SCORE_WEIGHT_OPEN_PORT_THRESHOLD:
                        score += self.SCORE_WEIGHT_MANY_OPEN_PORTS
                        factors.append(f"开放端口 {open_ports}")

                    # 事件相关
                    open_inc = incident_stats.get(str(asset.id), 0)
                    score += open_inc * self.SCORE_WEIGHT_OPEN_INCIDENT
                    if open_inc > 0:
                        factors.append(f"未关闭事件 {open_inc}")

                    # 告警相关
                    alert_24h = alert_stats.get(asset.asset_ip, 0)
                    score += alert_24h * self.SCORE_WEIGHT_ALERT
                    if alert_24h > 0:
                        factors.append(f"24h 告警 {alert_24h}")

                    # 命中 D6 任意一条才算高危
                    is_high_risk = self._is_high_risk(
                        criticality=asset.criticality,
                        open_incidents=open_inc,
                        alert_24h=alert_24h,
                        high_risk_ports=high_risk_ports,
                    )
                    if not is_high_risk:
                        continue

                    scored.append({
                        "id": str(asset.id),
                        "ip": asset.asset_ip,
                        "name": asset.name or asset.asset_ip,
                        "asset_type": asset.asset_type,
                        "criticality": asset.criticality,
                        "score": score,
                        "factors": factors,
                    })
                except Exception as e:
                    logger.warning(f"单资产评分失败,跳过(id={asset.id}): {e}")
                    continue

            # 评分降序,再按 IP 升序稳定排序
            scored.sort(key=lambda x: (-x["score"], x["ip"]))
            return scored[:limit]
        except Exception as e:
            logger.warning(f"高危资产评分失败: {e}")
            return []

    def _is_high_risk(
        self,
        criticality: Optional[str],
        open_incidents: int,
        alert_24h: int,
        high_risk_ports: int,
    ) -> bool:
        """
        D6 高危资产定义:5 条件命中任一
        1. criticality='core' AND (alert_24h>0 OR high_risk_ports>0 OR open_incidents>0)
        2. open_incidents>0
        3. alert_24h>=10
        """
        if open_incidents > 0:
            return True
        if alert_24h >= self.HIGH_RISK_ALERT_THRESHOLD:
            return True
        if criticality == "core" and (alert_24h > 0 or high_risk_ports > 0 or open_incidents > 0):
            return True
        return False

    def _aggregate_port_stats(self, asset_ids: List) -> Dict[str, Dict[str, int]]:
        """
        聚合每个资产的端口统计
        返回:{asset_id_str: {"open": N, "high_risk": M}}
        """
        try:
            rows = (
                self.db.query(
                    AssetPort.asset_id,
                    func.count(AssetPort.id).label("total"),
                    func.sum(
                        case((AssetPort.port.in_(list(HIGH_RISK_PORT_NUMBERS)), 1), else_=0)
                    ).label("high_risk"),
                )
                .filter(AssetPort.asset_id.in_(asset_ids), AssetPort.state == "open")
                .group_by(AssetPort.asset_id)
                .all()
            )
            return {
                str(row.asset_id): {
                    "open": int(row.total or 0),
                    "high_risk": int(row.high_risk or 0),
                }
                for row in rows
            }
        except Exception as e:
            logger.warning(f"端口统计聚合失败: {e}")
            return {}

    def _aggregate_incident_stats(self, asset_ids: List) -> Dict[str, int]:
        """聚合每个资产的未关闭事件数"""
        try:
            rows = (
                self.db.query(
                    AssetIncident.asset_id,
                    func.count(AssetIncident.incident_id).label("total"),
                )
                .join(Incident, AssetIncident.incident_id == Incident.id)
                .filter(
                    AssetIncident.asset_id.in_(asset_ids),
                    Incident.status.in_(["open", "in_progress", "resolved"]),
                )
                .group_by(AssetIncident.asset_id)
                .all()
            )
            return {str(row.asset_id): int(row.total or 0) for row in rows}
        except Exception as e:
            logger.warning(f"事件统计聚合失败: {e}")
            return {}

    def _aggregate_alert_stats(self, asset_ips: List[str]) -> Dict[str, int]:
        """
        聚合每个资产 IP 的 24h 告警数

        Phase 2 接 OpenSearch 后改为按 agent.ip 聚合。
        当前 mock:只把 mock_top 里的 IP 返回硬编码值,其他 IP 返回 0。
        """
        try:
            alert_service = AlertQueryService(self.db)
            top_alert_assets = alert_service.get_top_alert_assets(hours=24, limit=50)
            return {row["ip"]: int(row.get("alert_count", 0)) for row in top_alert_assets}
        except Exception as e:
            logger.warning(f"告警统计聚合失败: {e}")
            return {}

    # ---------- 5. Top Alert Assets ----------

    def _build_top_alert_assets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        告警数前 10 资产(IP 维度)

        走 AlertQueryService.get_top_alert_assets(),
        返回后和资产表 LEFT JOIN 拿到 name/asset_type/id(用于详情页跳转)
        """
        try:
            alert_service = AlertQueryService(self.db)
            top = alert_service.get_top_alert_assets(hours=24, limit=limit)
            if not top:
                return []

            # 用 IP 反查资产
            ips = [row.get("ip") for row in top if row.get("ip")]
            assets_by_ip: Dict[str, Asset] = {}
            if ips:
                try:
                    asset_rows = self.db.query(Asset).filter(Asset.asset_ip.in_(ips)).all()
                    assets_by_ip = {a.asset_ip: a for a in asset_rows}
                except Exception as e:
                    logger.warning(f"反查资产信息失败: {e}")

            result: List[Dict[str, Any]] = []
            for row in top:
                ip = row.get("ip", "")
                asset = assets_by_ip.get(ip)
                result.append({
                    "id": str(asset.id) if asset else None,
                    "ip": ip,
                    "name": (asset.name if asset and asset.name else ip),
                    "asset_type": (asset.asset_type if asset else None),
                    "alert_24h": int(row.get("alert_count", 0)),
                    "alert_critical_24h": int(row.get("critical_count", 0)),
                    "last_alert_at": row.get("last_alert_at"),
                })
            return result
        except Exception as e:
            logger.warning(f"Top 告警资产获取失败: {e}")
            return []
