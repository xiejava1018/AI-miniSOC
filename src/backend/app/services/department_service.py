"""Department Service"""
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session

from app.models.department import Department
from app.schemas.department import DepartmentCreate, DepartmentUpdate


class DepartmentService:
    """部门服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_departments(
        self,
        skip: int = 0,
        limit: int = 20,
        name: Optional[str] = None,
        status: Optional[int] = None
    ) -> Tuple[List[Department], int]:
        """
        获取部门列表

        Args:
            skip: 跳过记录数
            limit: 返回记录数
            name: 部门名称搜索
            status: 状态筛选

        Returns:
            (部门列表, 总数)
        """
        query = self.db.query(Department)

        if name:
            query = query.filter(Department.name.ilike(f"%{name}%"))

        if status is not None:
            query = query.filter(Department.status == status)

        total = query.count()
        departments = query.order_by(Department.sort).offset(skip).limit(limit).all()

        return departments, total

    def get_department_by_id(self, department_id: int) -> Department:
        """根据ID获取部门"""
        department = self.db.query(Department).filter(Department.id == department_id).first()
        if not department:
            raise ValueError("部门不存在")
        return department

    def create_department(self, data: DepartmentCreate) -> Department:
        """
        创建部门

        Args:
            data: 部门创建数据

        Returns:
            创建的部门对象
        """
        department = Department(
            name=data.name,
            status=data.status,
            sort=data.sort
        )
        self.db.add(department)
        self.db.commit()
        self.db.refresh(department)
        return department

    def update_department(self, department_id: int, data: DepartmentUpdate) -> Department:
        """
        更新部门

        Args:
            department_id: 部门ID
            data: 更新数据

        Returns:
            更新后的部门

        Raises:
            ValueError: 部门不存在
        """
        department = self.get_department_by_id(department_id)

        if data.name is not None:
            department.name = data.name
        if data.status is not None:
            department.status = data.status
        if data.sort is not None:
            department.sort = data.sort

        self.db.commit()
        self.db.refresh(department)
        return department

    def delete_department(self, department_id: int) -> None:
        """
        删除部门

        Args:
            department_id: 部门ID

        Raises:
            ValueError: 部门不存在或有用户关联
        """
        department = self.get_department_by_id(department_id)

        # 检查是否有用户关联
        user_count = len(department.users) if department.users else 0
        if user_count > 0:
            raise ValueError(f"该部门有 {user_count} 个用户关联，无法删除")

        self.db.delete(department)
        self.db.commit()

    def get_all_departments(self) -> List[Department]:
        """获取所有部门（不分页，用于下拉选择）"""
        return self.db.query(Department).filter(Department.status == 1).order_by(Department.sort).all()
