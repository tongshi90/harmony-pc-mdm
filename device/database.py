"""设备模拟库：仅指向 device/data/device.db，不触碰云侧 mdm.db 写路径."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from device.config import settings

# 复用云侧 ORM 模型元数据建表；引擎与会话独立
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402 — 注册全部表

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_schema() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
