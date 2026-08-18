#!/usr/bin/env python3
"""CI 专用：用 SQLAlchemy Base.metadata.create_all 创建所有表（model 即 schema）。

历史原因：alembic 升级 head 在空库失败，因 soc_menus.component / permissions 列是手工 ALTER 加过
但 alembic 历史里没迁移记录（schema 比 migration 领先）。本脚本直接用 SQLAlchemy model 当 schema 准。
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

from dotenv import load_dotenv
load_dotenv()  # CI 没 .env, 但无害

from app.core.database import engine
from app.models import Base


def main() -> None:
    print("开始创建数据库表 (Base.metadata.create_all)...")
    Base.metadata.create_all(bind=engine)
    print("✅ 创建表成功")

    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"总 {len(tables)} 张表")
    for t in sorted(tables):
        print(f"  - {t}")


if __name__ == "__main__":
    main()