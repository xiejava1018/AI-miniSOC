#!/usr/bin/env python3
"""
添加前端允许主机配置项
"""
import sys
import os

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import SystemConfig


def main():
    """添加前端允许主机配置"""
    print("添加前端允许主机配置...")

    db = SessionLocal()

    try:
        # 检查是否已存在
        existing = db.query(SystemConfig).filter(
            SystemConfig.category == "frontend",
            SystemConfig.key == "allowed_hosts",
        ).first()

        if existing:
            print(f"  ⚠️  配置项已存在，更新值")
            existing.value = "localhost,.localhost,aisoc.doai8.dpdns.org,192.168.0.128,192.168.199.143"
            existing.description = "前端允许访问的主机名（逗号分隔，修改后需重启前端服务）"
        else:
            print(f"  ✅ 创建新配置项")
            config = SystemConfig(
                category="frontend",
                key="allowed_hosts",
                value="localhost,.localhost,aisoc.doai8.dpdns.org,192.168.0.128,192.168.199.143",
                value_type="string",
                description="前端允许访问的主机名（逗号分隔，修改后需重启前端服务）"
            )
            db.add(config)

        db.commit()
        print("\n✅ 配置项添加成功！")
        print("\n配置信息:")
        print("  分类: frontend")
        print("  键名: allowed_hosts")
        print("  值: localhost,.localhost,aisoc.doai8.dpdns.org,192.168.0.128,192.168.199.143")
        print("\n⚠️  注意: 修改此配置后需要重启前端服务才能生效！")
        print("   可通过系统管理 -> 系统配置界面进行修改")

    except Exception as e:
        print(f"\n❌ 添加失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
