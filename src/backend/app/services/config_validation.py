"""配置值 schema 校验（路线 C 配套：堵住绕过前端校验的路径）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.4 / §6.4
- soc_config_schema 注册的配置项：写入前按 value_type + validation 校验
- editable=False 的项：拒绝写入（如 allowed_hosts 等运行时事实）
- 已注册 schema 的项：禁止删除（防止删键后业务模块静默回落默认值）
- 未注册的项：放行（兜底，兼容开发期临时键）
"""
from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.config_schema import ConfigSchema


def get_schema(db: Session, category: str, key: str) -> Optional[ConfigSchema]:
    return (
        db.query(ConfigSchema)
        .filter(ConfigSchema.category == category, ConfigSchema.key == key)
        .first()
    )


def validate_value(db: Session, category: str, key: str, value: str) -> None:
    """按 schema 校验配置值。不合法抛 ValueError（API 层转 400）。

    未注册 schema 的键放行（兜底语义，规格 §6.4）。
    """
    schema = get_schema(db, category, key)
    if schema is None:
        return

    label = schema.label or f"{category}.{key}"

    if not schema.editable:
        raise ValueError(f"「{label}」为只读配置项，不允许通过界面修改")

    vtype = schema.value_type
    val = value if value is not None else ""
    vrules = schema.validation or {}

    if vtype == "boolean":
        if str(val).strip().lower() not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError(f"「{label}」需要布尔值（true/false），收到: {val!r}")

    elif vtype == "number":
        try:
            num = float(str(val).strip())
        except (TypeError, ValueError):
            raise ValueError(f"「{label}」需要数字，收到: {val!r}")
        if "min" in vrules and num < vrules["min"]:
            raise ValueError(f"「{label}」不能小于 {vrules['min']}，收到: {num}")
        if "max" in vrules and num > vrules["max"]:
            raise ValueError(f"「{label}」不能大于 {vrules['max']}，收到: {num}")

    elif vtype == "json":
        try:
            json.loads(val if str(val).strip() else "{}")
        except (TypeError, ValueError) as e:
            raise ValueError(f"「{label}」不是合法 JSON: {e}")

    else:  # string / multiline / password / list
        if "maxLength" in vrules and len(str(val)) > vrules["maxLength"]:
            raise ValueError(f"「{label}」长度不能超过 {vrules['maxLength']} 字符")
        pattern = vrules.get("pattern")
        if pattern:
            try:
                if not re.fullmatch(pattern, str(val)):
                    raise ValueError(
                        f"「{label}」格式不符合要求（pattern: {pattern}），收到: {str(val)[:50]!r}"
                    )
            except re.error:
                # schema 里正则本身写错时不阻断写入，只记日志
                pass


def validate_delete(db: Session, category: str, key: str) -> None:
    """已注册 schema 的配置项禁止删除（防删键后业务静默回落默认值）。"""
    schema = get_schema(db, category, key)
    if schema is not None:
        raise ValueError(
            f"「{schema.label or f'{category}.{key}'}」是已注册的受管配置项，不允许删除"
            f"（删除会导致业务模块静默回落默认值；如需停用请调整其值）"
        )
