from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# 注册 SQLite 建表时把 Column.comment 写入 DDL
import app.database_comments  # noqa: F401

# SQLite 并发：busy_timeout 等待写锁；WAL 允许多读一写，减轻 database is locked
_SQLITE_CONNECT_ARGS = {
    "check_same_thread": False,
    "timeout": 30,
}

engine = create_engine(
    settings.database_url,
    connect_args=_SQLITE_CONNECT_ARGS,
    pool_pre_ping=True,
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
