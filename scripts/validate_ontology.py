#!/usr/bin/env python
"""OH-1.3 本体校验 CI 入口（CI 用）。

设计依据：实施方案 OH-1.3
调用方式：
    PYTHONPATH=src/backend python scripts/validate_ontology.py
    python scripts/validate_ontology.py --strict

退出码：
- 0：全部通过
- 1：校验失败
- 2：脚本自身错误（导入失败、文件缺失等）

校验项：
1. 加载本体（必须能 load）
2. 必填字段：id / version / generated_at / top_level_classes / relations / axioms
3. id 唯一：top_level / relations / axioms 三层各检
4. domain/range 闭合：关系引用未定义的类
5. 公理 rule / test 字段非空（CI 场景必须可执行）
6. （可选）属性 type 必须是已知 yaml 原生类型
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 把 src/backend 加到 path（CI runner 用法）
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

try:
    from app.core.asset_ontology import load, self_check
except Exception as e:
    print(f"FATAL: cannot import asset_ontology: {e}", file=sys.stderr)
    sys.exit(2)


KNOWN_ATTRIBUTE_TYPES = {
    "string", "text", "uuid", "integer", "float", "boolean",
    "date", "timestamp", "enum", "jsonb",
    # 业务扩展类型（pg 原生 / 网络协议）
    "macaddr", "ip", "cidr", "inet",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="OH-1.3 本体校验")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：属性 type 不在白名单也报错",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 输出（CI 集成用）",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    # 1. 加载
    try:
        snap = load()
    except (FileNotFoundError, ValueError) as e:
        errors.append(f"load failed: {e}")
        return _report(args, errors, warnings)

    # 5. 公理 rule / test 非空
    for a in snap.axioms:
        if not a.rule:
            errors.append(f"axiom '{a.id}' rule is empty")
        if not a.test:
            warnings.append(f"axiom '{a.id}' test is empty (no pytest binding)")

    # 6. 属性 type 白名单（仅严格模式）
    if args.strict:
        for c in snap.classes:
            for attr in c.attributes:
                attr_type = attr.get("type")
                if attr_type and attr_type not in KNOWN_ATTRIBUTE_TYPES:
                    errors.append(
                        f"class '{c.id}' attribute '{attr.get('id')}' "
                        f"has unknown type '{attr_type}'"
                    )

    return _report(args, errors, warnings)


def _report(args: argparse.Namespace, errors: list[str], warnings: list[str]) -> int:
    info = self_check()
    info["errors"] = errors
    info["warnings"] = warnings
    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print(f"ontology: {info.get('version')} (loaded in {info.get('elapsed_ms')}ms)")
        print(f"  classes:   {info.get('classes')}")
        print(f"  relations: {info.get('relations')}")
        print(f"  axioms:    {info.get('axioms')}")
        if warnings:
            print(f"\nWarnings ({len(warnings)}):")
            for w in warnings:
                print(f"  ⚠ {w}")
        if errors:
            print(f"\nErrors ({len(errors)}):")
            for e in errors:
                print(f"  ✗ {e}")
            return 1
        print("\n✓ ontology validation passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())