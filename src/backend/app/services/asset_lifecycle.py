"""
资产生命周期服务（PRD F3.2 / v1.2.1）

防幻觉设计（PRD v1.2 修订，弃 WebSearch 主路径）：
- EOL 主路径 = 预置参考表（soc_eol_reference，endoflife.date 公开口径 + 人工维护）
- 用户手动覆盖优先（expected_eol_source='manual'），刷新永不触碰，覆盖/恢复落审计
- 匹配：规范化 OS 标签（去 "gnu/linux"/" linux" 噪声词）→ 子串匹配，最长模式优先

与风险评分的关系：asset_risk 的 health 维度有独立的 eol_systems 兜底配置
（无漏洞扫描数据时使用），本表是生命周期模块的主数据源；两者口径独立（PRD：
本 PRD 不改动既有评分），后续迭代可统一消费本表。
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset
from app.models.audit_log import AuditLog
from app.models.eol_reference import EolReference

logger = logging.getLogger(__name__)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def normalize_os_label(asset: Asset) -> str:
    """规范化 os_name + os_version 为匹配标签。

    'Ubuntu Linux 24.04 LTS' → 'ubuntu 24.04 lts'
    'Debian GNU/Linux 12'    → 'debian 12'
    'CentOS Linux 7.9'       → 'centos 7.9'
    """
    label = f"{asset.os_name or ''} {asset.os_version or ''}".lower()
    label = label.replace("gnu/linux", " ")
    label = label.replace(" linux", " ")
    return " ".join(label.split())


class AssetLifecycleService:
    def __init__(self, db: Session):
        self.db = db
        self._refs: Optional[list] = None

    # ---------- 匹配引擎 ----------

    def _load_refs(self) -> list:
        """参考表一次性加载（~30 行），避免批量刷新时 N 次查询。"""
        if self._refs is None:
            self._refs = self.db.query(EolReference).filter(EolReference.enabled.is_(True)).all()
        return self._refs

    def _match_reference(self, asset: Asset) -> Optional[EolReference]:
        """最长模式优先的子串匹配。"""
        label = normalize_os_label(asset)
        if not label:
            return None
        best = None
        for ref in self._load_refs():
            if ref.pattern.lower() in label:
                if best is None or len(ref.pattern) > len(best.pattern):
                    best = ref
        return best

    def refresh_eol_all(self) -> dict:
        """按参考表回填全部资产的 expected_eol。

        manual 覆盖跳过（PRD：覆盖优先）；无匹配且有 os 信息的清空旧 preset 值
        （OS 可能已变更）；无 os 信息保持不动。
        """
        stats = {"matched": 0, "cleared": 0, "kept_manual": 0, "no_os": 0, "unmatched": 0}
        for asset in self.db.query(Asset).all():
            if (asset.expected_eol_source or "preset") == "manual":
                stats["kept_manual"] += 1
                continue
            if not asset.os_name:
                stats["no_os"] += 1
                continue
            ref = self._match_reference(asset)
            if ref:
                asset.expected_eol = ref.eol_date
                asset.expected_eol_source = "preset"
                stats["matched"] += 1
            else:
                if asset.expected_eol is not None:
                    asset.expected_eol = None
                    stats["cleared"] += 1
                else:
                    stats["unmatched"] += 1
        self.db.commit()
        logger.info("EOL 刷新完成: %s", stats)
        return stats

    # ---------- 手动覆盖 / 恢复（审计） ----------

    def set_eol_override(self, asset_id, eol_date: date, user) -> Optional[Asset]:
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return None
        old = asset.expected_eol.isoformat() if asset.expected_eol else None
        asset.expected_eol = eol_date
        asset.expected_eol_source = "manual"
        self.db.add(AuditLog(
            user_id=user.id, username=user.username, action="update",
            resource_type="asset", resource_id=None,
            resource_name=f"asset:{asset_id}:eol",
            old_values={"expected_eol": old, "source": "preset"},
            new_values={"expected_eol": eol_date.isoformat(), "source": "manual"},
            status="success",
        ))
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def clear_eol_override(self, asset_id, user) -> Optional[Asset]:
        """恢复自动匹配：立即按参考表重算（无匹配则置空）。"""
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return None
        old = asset.expected_eol.isoformat() if asset.expected_eol else None
        ref = self._match_reference(asset) if asset.os_name else None
        asset.expected_eol = ref.eol_date if ref else None
        asset.expected_eol_source = "preset"
        self.db.add(AuditLog(
            user_id=user.id, username=user.username, action="update",
            resource_type="asset", resource_name=f"asset:{asset_id}:eol",
            old_values={"expected_eol": old, "source": "manual"},
            new_values={"expected_eol": asset.expected_eol.isoformat() if asset.expected_eol else None,
                        "source": "preset"},
            status="success",
        ))
        self.db.commit()
        self.db.refresh(asset)
        return asset

    # ---------- 总览（退役/升级建议列表，PRD 核心输出） ----------

    @staticmethod
    def _days_left(d: Optional[date]) -> Optional[int]:
        if d is None:
            return None
        return (d - _today()).days

    def overview(self) -> dict:
        today = _today()
        eol_expired, eol_30, eol_90 = [], [], []
        w_expired, w_30 = [], []

        assets = self.db.query(Asset).filter(
            (Asset.expected_eol.isnot(None)) | (Asset.warranty_end.isnot(None))
        ).all()
        for a in assets:
            base = {
                "asset_id": str(a.id), "name": a.name, "ip": a.asset_ip,
                "os": f"{a.os_name or ''} {a.os_version or ''}".strip(),
            }
            if a.expected_eol is not None:
                days = (a.expected_eol - today).days
                item = {**base, "eol_date": a.expected_eol.isoformat(), "days_left": days,
                        "source": a.expected_eol_source}
                # 口径透出（PRD 防幻觉）：preset 命中的参考条目名 + 是否待人工核实
                if (a.expected_eol_source or "preset") != "manual":
                    ref = self._match_reference(a)
                    if ref:
                        item["eol_ref"] = ref.display_name
                        item["eol_unverified"] = ref.source == "preset_unverified"
                        item["eol_note"] = ref.notes
                if days < 0:
                    eol_expired.append(item)
                elif days <= 30:
                    eol_30.append(item)
                elif days <= 90:
                    eol_90.append(item)
            if a.warranty_end is not None:
                wdays = (a.warranty_end - today).days
                item = {**base, "warranty_end": a.warranty_end.isoformat(), "warranty_days_left": wdays}
                if wdays < 0:
                    w_expired.append(item)
                elif wdays <= 30:
                    w_30.append(item)
        for lst in (eol_expired, eol_30, eol_90, w_expired, w_30):
            lst.sort(key=lambda x: x.get("days_left", x.get("warranty_days_left", 0)))

        # 待匹配提示：有 OS 但无 EOL 值（非 manual）的资产数
        unmatched = (
            self.db.query(Asset)
            .filter(
                Asset.os_name.isnot(None),
                Asset.expected_eol.is_(None),
                (Asset.expected_eol_source != "manual"),
            )
            .count()
        )
        return {
            "eol_expired": eol_expired, "eol_within_30d": eol_30, "eol_within_90d": eol_90,
            "warranty_expired": w_expired, "warranty_within_30d": w_30,
            "unmatched_count": unmatched,
        }
