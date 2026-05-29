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

        Raises:
            ValueError: 父部门不存在
        """
        # 检查父部门是否存在
        if data.parent_id is not None:
            self.get_department_by_id(data.parent_id)

        department = Department(
            name=data.name,
            parent_id=data.parent_id,
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
            ValueError: 部门不存在或循环引用
        """
        department = self.get_department_by_id(department_id)

        if data.name is not None:
            department.name = data.name
        if data.parent_id is not None and data.parent_id != department_id:
            # 防止循环引用：不能将自己或自己的子部门设为父部门
            if data.parent_id == department_id:
                raise ValueError("不能将自己设为上级部门")
            # 检查 parent_id 是否是自己的子部门
            descendants = self._get_descendant_ids(department_id)
            if data.parent_id in descendants:
                raise ValueError("不能将子部门设为上级部门")
            department.parent_id = data.parent_id
        if data.status is not None:
            department.status = data.status
        if data.sort is not None:
            department.sort = data.sort

        self.db.commit()
        self.db.refresh(department)
        return department

    def _get_descendant_ids(self, department_id: int) -> set:
        """递归获取所有子部门的ID"""
        ids = set()
        children = self.db.query(Department).filter(Department.parent_id == department_id).all()
        for child in children:
            ids.add(child.id)
            ids.update(self._get_descendant_ids(child.id))
        return ids

    def delete_department(self, department_id: int) -> None:
        """
        删除部门

        Args:
            department_id: 部门ID

        Raises:
            ValueError: 部门不存在或有用户关联或有子部门
        """
        department = self.get_department_by_id(department_id)

        # 检查是否有用户关联
        user_count = len(department.users) if department.users else 0
        if user_count > 0:
            raise ValueError(f"该部门有 {user_count} 个用户关联，无法删除")

        # 检查是否有子部门
        child_count = self.db.query(Department).filter(Department.parent_id == department_id).count()
        if child_count > 0:
            raise ValueError(f"该部门有 {child_count} 个子部门，无法删除")

        self.db.delete(department)
        self.db.commit()

    def get_all_departments(self) -> List[Department]:
        """获取所有部门（不分页，用于下拉选择）"""
        return self.db.query(Department).filter(Department.status == 1).order_by(Department.sort).all()

    def get_department_tree(self) -> List[dict]:
        """获取部门树形结构"""
        # 查询所有顶级部门
        root_departments = self.db.query(Department).filter(Department.parent_id == None).order_by(Department.sort).all()
        result = []
        for dept in root_departments:
            result.append(self._build_tree_node(dept))
        return result

    def _build_tree_node(self, department: Department) -> dict:
        """递归构建树节点"""
        children = self.db.query(Department).filter(Department.parent_id == department.id).order_by(Department.sort).all()
        user_count = len(department.users) if department.users else 0
        node = {
            "id": department.id,
            "parent_id": department.parent_id,
            "name": department.name,
            "status": department.status,
            "sort": department.sort,
            "user_count": user_count,
        }
        if children:
            node["children"] = [self._build_tree_node(child) for child in children]
        return node
