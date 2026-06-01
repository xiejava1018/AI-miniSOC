#!/usr/bin/env python3
"""
迁移 soc_assets 表中静态枚举字段为字典 dict_code

历史问题:
  - asset_sync.py 之前把中文标签(在线/离线/从未连接)直接写入 asset_status 列
  - 旧的人工录入数据中 criticality/asset_type/data_source 可能为 NULL

本脚本把所有"老格式"数据规范成字典中定义的 dict_code。
"""
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.core.database import SessionLocal


# 字段名 -> {旧值: 新值(字典 dict_code)}
MIGRATIONS = {
    "asset_status": {
        "在线": "online",
        "离线": "offline",
        "从未连接": "never_connected",
        "已下线": "decommissioned",
        "新发现": "never_connected",  # 历史脏数据，归一为 never_connected
        "未知": "unknown",
        "": "unknown",
    },
    "criticality": {
        # 已存在的英文 code 与 severity 字典一致，无需转换
        # 修复历史脏数据
        "核心": "critical",
        "重要": "high",
        "普通": "medium",
        "低": "low",
        "中": "medium",
        "高": "high",
        "严重": "critical",
    },
    "asset_type": {
        "服务器": "server",
        "工作站": "workstation",
        "网络设备": "network_device",
        "安全设备": "security_device",
        "其他": "other",
    },
    "data_source": {
        "Wazuh": "wazuh",
        "wazuh": "wazuh",
        "手动录入": "manual",
        "manual": "manual",
    },
}

# 字段名 -> 兜底默认值 (用于把 NULL 设为合理默认值)
DEFAULTS = {
    "criticality": "medium",
    "asset_type": "other",
    "data_source": "manual",
    "asset_status": "unknown",
}


def run():
    db = SessionLocal()
    try:
        print("=== soc_assets 字典化迁移 ===\n")

        # 1) 转换已知的中文/脏值 -> 英文 dict_code
        for col, mapping in MIGRATIONS.items():
            for old, new in mapping.items():
                if old == new:
                    continue
                # NULL 不参与
                result = db.execute(
                    text(
                        f"UPDATE soc_assets SET {col} = :new "
                        f"WHERE {col} = :old"
                    ),
                    {"old": old, "new": new},
                )
                if result.rowcount > 0:
                    print(f"  ✅ {col}: '{old}' -> '{new}' 影响 {result.rowcount} 行")

        # 2) 把 NULL 字段补默认值
        for col, default in DEFAULTS.items():
            result = db.execute(
                text(
                    f"UPDATE soc_assets SET {col} = :default "
                    f"WHERE {col} IS NULL OR {col} = ''"
                ),
                {"default": default},
            )
            if result.rowcount > 0:
                print(f"  ✅ {col}: NULL/'' -> '{default}' 影响 {result.rowcount} 行")

        db.commit()

        # 3) 验证迁移结果
        print("\n=== 迁移后字段值分布 ===")
        for col in MIGRATIONS.keys():
            print(f"\n--- {col} ---")
            rows = db.execute(
                text(
                    f"SELECT {col}, COUNT(*) FROM soc_assets "
                    f"GROUP BY {col} ORDER BY 2 DESC"
                )
            ).fetchall()
            for r in rows:
                print(f"  {repr(r[0])}: {r[1]}")

        print("\n✅ 迁移完成")
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
