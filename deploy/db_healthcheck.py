#!/usr/bin/env python3
"""DB 探活脚本（deploy.sh 和 deploy-prod.yml 共用）。

从环境变量读 DB 连接信息（不依赖 psql，服务器可能没装 postgresql-client）：
  DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASS

成功输出 "1"（SELECT 1 结果），失败抛异常退出非 0。
"""
import os
import sys

from urllib.parse import quote_plus


def main() -> int:
    host = os.environ.get("DB_HOST", "")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "")
    user = os.environ.get("DB_USER", "")
    password = os.environ.get("DB_PASS", "")

    if not host or not name:
        print("ERROR: missing DB_HOST or DB_NAME env var", file=sys.stderr)
        return 2

    from sqlalchemy import create_engine, text

    pw = quote_plus(password)
    url = f"postgresql://{user}:{pw}@{host}:{port}/{name}"
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())