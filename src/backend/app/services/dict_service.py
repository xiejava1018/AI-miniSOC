"""字典 Service"""

from typing import Tuple, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from app.models.dict import Dict
from app.schemas.dict import DictCreate, DictUpdate


class DictService:
    """字典服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        dict_type: Optional[str] = None,
    ) -> Tuple[List[Dict], int]:
        """
        获取字典列表（分页）

        Args:
            skip: 跳过记录数
            limit: 返回记录数
            search: 搜索关键词（匹配 dict_code / dict_label）
            dict_type: 按字典类型筛选

        Returns:
            (字典列表, 总数)
        """
        query = self.db.query(Dict)

        if dict_type:
            query = query.filter(Dict.dict_type == dict_type)

        if search:
            pattern = f"%{search}%"
            query = query.filter(
                (Dict.dict_code.ilike(pattern)) | (Dict.dict_label.ilike(pattern))
            )

        total = query.count()
        items = (
            query.order_by(Dict.dict_type, Dict.sort_order, Dict.id)
            .offset(skip)
            .limit(limit)
            .all()
        )

        return items, total

    def get_by_type(self, dict_type: str) -> List[Dict]:
        """按类型获取全部字典项（不分页，前端缓存用）"""
        return (
            self.db.query(Dict)
            .filter(Dict.dict_type == dict_type, Dict.is_active == True)
            .order_by(Dict.sort_order, Dict.id)
            .all()
        )

    def get_all_types(self) -> List[str]:
        """获取所有字典分类（distinct dict_type）"""
        rows = (
            self.db.query(Dict.dict_type)
            .distinct()
            .order_by(Dict.dict_type)
            .all()
        )
        return [r[0] for r in rows]

    def get_by_id(self, dict_id: int) -> Dict:
        """根据ID获取字典项"""
        item = self.db.query(Dict).filter(Dict.id == dict_id).first()
        if not item:
            raise ValueError("字典项不存在")
        return item

    def create(self, data: DictCreate) -> Dict:
        """
        创建字典项

        Raises:
            ValueError: 同类型下编码已存在
        """
        existing = (
            self.db.query(Dict)
            .filter(Dict.dict_type == data.dict_type, Dict.dict_code == data.dict_code)
            .first()
        )
        if existing:
            raise ValueError(f"字典类型 '{data.dict_type}' 下编码 '{data.dict_code}' 已存在")

        item = Dict(
            dict_type=data.dict_type,
            dict_code=data.dict_code,
            dict_label=data.dict_label,
            color=data.color,
            sort_order=data.sort_order,
            is_active=data.is_active,
            is_default=data.is_default,
            remark=data.remark,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, dict_id: int, data: DictUpdate) -> Dict:
        """
        更新字典项

        Raises:
            ValueError: 字典项不存在或编码冲突
        """
        item = self.get_by_id(dict_id)

        # 如果修改了 dict_type 或 dict_code，检查唯一约束
        new_type = data.dict_type if data.dict_type is not None else item.dict_type
        new_code = data.dict_code if data.dict_code is not None else item.dict_code
        if new_type != item.dict_type or new_code != item.dict_code:
            conflict = (
                self.db.query(Dict)
                .filter(Dict.dict_type == new_type, Dict.dict_code == new_code, Dict.id != dict_id)
                .first()
            )
            if conflict:
                raise ValueError(f"字典类型 '{new_type}' 下编码 '{new_code}' 已存在")

        if data.dict_type is not None:
            item.dict_type = data.dict_type
        if data.dict_code is not None:
            item.dict_code = data.dict_code
        if data.dict_label is not None:
            item.dict_label = data.dict_label
        if data.color is not None:
            item.color = data.color
        if data.sort_order is not None:
            item.sort_order = data.sort_order
        if data.is_active is not None:
            item.is_active = data.is_active
        if data.is_default is not None:
            item.is_default = data.is_default
        if data.remark is not None:
            item.remark = data.remark

        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, dict_id: int) -> None:
        """
        删除字典项

        Raises:
            ValueError: 字典项不存在
        """
        item = self.get_by_id(dict_id)
        self.db.delete(item)
        self.db.commit()

    def get_type_codes(self, dict_type: str) -> List[str]:
        """取某类型所有 code（校验用）"""
        rows = (
            self.db.query(Dict.dict_code)
            .filter(Dict.dict_type == dict_type, Dict.is_active == True)
            .all()
        )
        return [r[0] for r in rows]
