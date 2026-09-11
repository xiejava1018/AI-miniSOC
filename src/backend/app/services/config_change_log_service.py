"""配置变更审计查询服务"""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.config_change_log import ConfigChangeLog


class ConfigChangeLogService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        target_type: Optional[str] = None,
        action: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[ConfigChangeLog], int]:
        q = self.db.query(ConfigChangeLog)
        if target_type:
            q = q.filter(ConfigChangeLog.target_type == target_type)
        if action:
            q = q.filter(ConfigChangeLog.action == action)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                (ConfigChangeLog.target_key.ilike(pattern))
                | (ConfigChangeLog.operator_ip.ilike(pattern))
            )
        total = q.count()
        items = (
            q.order_by(ConfigChangeLog.created_at.desc(), ConfigChangeLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total