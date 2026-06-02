"""
公共系统信息 API（不需要鉴权）

返回前台展示用系统元信息（应用名称 / Logo / 版权 / 描述）。
数据来源：soc_system_config 表 category='general' 的几条白名单 key。

**白名单机制**：只暴露指定 key，其它配置（如 SMTP、GLM_API_KEY 等）绝不返回，
避免任何敏感配置经此接口泄露。
"""
from typing import Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.system_config_service import SystemConfigService


router = APIRouter()

# 前台可暴露的 system.* 配置项白名单（key 列表）
PUBLIC_SYSTEM_KEYS = {
    "system_name": "AI-miniSOC",
    "system_logo": "",
    "system_copyright": "© 2026 AI-miniSOC",
    "system_description": "AI-driven mini Security Operation Center",
}


@router.get("/system-info")
async def get_public_system_info(db: Session = Depends(get_db)) -> Dict[str, str]:
    """
    返回系统前台展示用元信息。

    **不需要鉴权**：浏览器 <title> / 登录页 / 顶栏 / 关于弹窗在用户登录前就要显示。
    仅返回白名单 key 列表内的 value，其它配置项（即使 category=general）一律忽略。
    """
    service = SystemConfigService(db)
    db_items = service.get_by_category("general")

    # 用 DB 覆盖白名单默认值；未配置的 key 保留兜底
    result: Dict[str, str] = dict(PUBLIC_SYSTEM_KEYS)
    for item in db_items:
        if item.key in PUBLIC_SYSTEM_KEYS:
            result[item.key] = item.value or PUBLIC_SYSTEM_KEYS[item.key]

    return result
