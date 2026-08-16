#!/usr/bin/env python3
"""
创建缺失的数据库表

P1-T2（数据可靠性）：历史一次性脚本，仅作为紧急恢复备用。
禁止生产环境调用，表结构变更一律走 alembic migration：
  cd src/backend && alembic upgrade head

保持此脚本仅为冷启动/灾备场景使用。
"""
import sys
import os

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import engine
from app.models import (
    Base, User, Role, Menu, RoleMenu,
    UserSession, SystemConfig, PasswordHistory,
    PasswordResetToken, AuditLog, RateLimit
)


def create_tables():
    """创建所有表（P1-T2：仅冷启动/灾备场景使用）"""
    print("开始创建数据库表...")

    # 创建所有表
    Base.metadata.create_all(bind=engine)

    print("✅ 数据库表创建成功！")

    # 显示已创建的表
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print("\n已创建的表:")
    for table in sorted(tables):
        print(f"  - {table}")


if __name__ == "__main__":
    create_tables()
