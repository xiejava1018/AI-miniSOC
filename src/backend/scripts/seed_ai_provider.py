"""AI Provider 种子：把 .env 的 GLM 回落配置落库为可见实例（2026-09-13）

目的：.env 回落是"看不见的配置"——界面空列表时用户不知道当前用什么模型。
本脚本把 GLM_API_* 三键导入为 `glm-main` 默认实例（is_default=true），
让回落配置在「AI 模型管理」界面可见、可编辑、可测试。

幂等：provider_code=glm-main 已存在则跳过（不覆盖用户后续的修改）。
执行：
    cd src/backend
    ../../venv/bin/python scripts/seed_ai_provider.py [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.ai_provider import AIProvider  # noqa: E402
from app.services.encryption_service import encryption_service  # noqa: E402

logger = logging.getLogger(__name__)

CODE = "glm-main"


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 .env GLM 为默认 AI Provider")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = getattr(settings, "GLM_API_KEY", None)
    if not api_key:
        logger.warning("GLM_API_KEY 未配置，无需导入（界面将显示 env 回落提示）")
        return 0

    base_url = (getattr(settings, "GLM_API_BASE", "") or "").rstrip("/")
    model = getattr(settings, "GLM_MODEL", "glm-4-flash")

    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        existing = db.query(AIProvider).filter(AIProvider.provider_code == CODE).first()
        if existing:
            logger.info("✅ %s 已存在（跳过，不覆盖用户修改）", CODE)
            return 0

        obj = AIProvider(
            provider_code=CODE,
            name="GLM（.env 导入）",
            base_url=base_url,
            protocol="openai",
            model_name=model,
            api_key=encryption_service.encrypt(api_key),
            scenes=[],
            max_tokens=None,
            timeout_seconds=60,
            enabled=True,
            is_default=True,
            remark="由 .env GLM_* 导入的回落配置；可编辑/停用，停用且无其他实例时仍回落 .env",
        )
        db.add(obj)
        if args.dry_run:
            db.rollback()
            logger.info("（dry-run）将导入 %s: %s / %s", CODE, base_url, model)
        else:
            db.commit()
            logger.info("✅ 已导入 %s: %s / %s（默认实例）", CODE, base_url, model)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
