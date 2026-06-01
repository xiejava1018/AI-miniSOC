"""系统配置 Service"""
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from app.models.system_config import SystemConfig
from app.schemas.system_config import SystemConfigCreate, SystemConfigUpdate


class SystemConfigService:
    """系统配置服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Tuple[List[SystemConfig], int]:
        """分页查询配置"""
        query = self.db.query(SystemConfig)

        if category:
            query = query.filter(SystemConfig.category == category)

        if search:
            pattern = f"%{search}%"
            query = query.filter(
                (SystemConfig.key.ilike(pattern))
                | (SystemConfig.value.ilike(pattern))
                | (SystemConfig.description.ilike(pattern))
            )

        total = query.count()
        items = (
            query.order_by(SystemConfig.category, SystemConfig.key)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    def get_by_id(self, config_id: int) -> SystemConfig:
        item = self.db.query(SystemConfig).filter(SystemConfig.id == config_id).first()
        if not item:
            raise ValueError("配置项不存在")
        return item

    def get_by_category_and_key(self, category: str, key: str) -> Optional[SystemConfig]:
        return (
            self.db.query(SystemConfig)
            .filter(SystemConfig.category == category, SystemConfig.key == key)
            .first()
        )

    def get_all_categories(self) -> List[dict]:
        """获取所有分类及数量"""
        rows = (
            self.db.query(SystemConfig.category, sql_func.count(SystemConfig.id))
            .group_by(SystemConfig.category)
            .order_by(SystemConfig.category)
            .all()
        )
        return [{"category": r[0], "count": r[1]} for r in rows]

    def get_by_category(self, category: str) -> List[SystemConfig]:
        """按分类取全部配置项（不分页）"""
        return (
            self.db.query(SystemConfig)
            .filter(SystemConfig.category == category)
            .order_by(SystemConfig.key)
            .all()
        )

    def create(self, data: SystemConfigCreate, user_id: Optional[int] = None) -> SystemConfig:
        """创建配置项"""
        existing = self.get_by_category_and_key(data.category, data.key)
        if existing:
            raise ValueError(f"配置项 [{data.category}.{data.key}] 已存在")

        item = SystemConfig(
            category=data.category,
            key=data.key,
            value=data.value,
            value_type=data.value_type,
            is_encrypted=data.is_encrypted,
            description=data.description,
            updated_by=user_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, config_id: int, data: SystemConfigUpdate, user_id: Optional[int] = None) -> SystemConfig:
        """更新配置项"""
        item = self.get_by_id(config_id)

        # 唯一性校验（修改了 category 或 key）
        new_category = data.category if data.category is not None else item.category
        new_key = data.key if data.key is not None else item.key
        if new_category != item.category or new_key != item.key:
            conflict = (
                self.db.query(SystemConfig)
                .filter(
                    SystemConfig.category == new_category,
                    SystemConfig.key == new_key,
                    SystemConfig.id != config_id,
                )
                .first()
            )
            if conflict:
                raise ValueError(f"配置项 [{new_category}.{new_key}] 已存在")

        if data.category is not None:
            item.category = data.category
        if data.key is not None:
            item.key = data.key
        if data.value is not None:
            item.value = data.value
        if data.value_type is not None:
            item.value_type = data.value_type
        if data.is_encrypted is not None:
            item.is_encrypted = data.is_encrypted
        if data.description is not None:
            item.description = data.description
        if user_id is not None:
            item.updated_by = user_id

        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, config_id: int) -> None:
        item = self.get_by_id(config_id)
        self.db.delete(item)
        self.db.commit()
