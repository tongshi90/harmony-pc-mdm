"""
设备模拟库初始化（写入 device/data/device.db，不影响云侧 data/mdm.db）。

用法（在仓库根目录或本目录执行）：

  .\\.venv\\Scripts\\python.exe device\\db_device_init.py
  .\\.venv\\Scripts\\python.exe device\\db_device_init.py --demo

逻辑复用根目录 db_init.py（建表 / 清空 / 种子），仅通过 MDM_DATABASE_URL 切到模拟库。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEVICE_DIR.parent
DB_PATH = DEVICE_DIR / "data" / "device.db"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 必须在导入 app / db_init 之前设置，才能让 settings.database_url 指向模拟库
os.environ["MDM_DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 若此前已导入过 app.config，强制按新 URL 重建引擎不现实；本脚本应独立进程运行
import app.config as app_config  # noqa: E402

app_config.settings.database_url = os.environ["MDM_DATABASE_URL"]

# 重建云侧 database 模块的引擎（db_init 依赖 SessionLocal / engine）
import app.database as app_db  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

app_db.engine = create_engine(
    app_config.settings.database_url,
    connect_args={"check_same_thread": False},
)
app_db.SessionLocal = sessionmaker(
    bind=app_db.engine, autoflush=False, autocommit=False
)

import db_init  # noqa: E402

# 让 db_init 使用我们刚替换的 engine / SessionLocal
db_init.engine = app_db.engine
db_init.SessionLocal = app_db.SessionLocal


def main() -> None:
    print(f"[device] 目标库: {DB_PATH}")
    db_init.main()
    print(f"[device] 完成。模拟库路径: {DB_PATH}")


if __name__ == "__main__":
    main()
