"""
数据库连接和会话管理
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# 同步数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    client_encoding='utf8'  # 设置客户端编码
)

# 同步 Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ---------------------------------------------------------------------------
# 独立测试库：完全与生产 DB 隔离
# 使用前需先创建库：CREATE DATABASE "AI-miniSOC-db_test";
# conftest 的 db_session fixture 用它做 create_all / drop_all，不污染生产数据
# ---------------------------------------------------------------------------
test_engine = create_engine(
    settings.TEST_DATABASE_URL,
    pool_pre_ping=True,
    client_encoding='utf8',
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
