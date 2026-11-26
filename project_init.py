"""
项目一键初始化：清业务数据，恢复为「刚部署完成」状态。

保留：
- 默认管理员 admin（初始密码见文档；库中以 bcrypt 哈希写入，启动后不覆盖）
- 系统预置角色（启动同源 bootstrap.ensure_system_roles）
- 操作日志保留天数等系统默认配置行（若服务侧有 ensure）
- data/rsa_*.pem（登录 RSA 密钥；删了也能跑，但会重新生成）

清除：
- SQLite：data/mdm.db（及 -wal/-shm）
- 应用/MDM 安装包等：data/uploads/
- 知识库上传与向量：data/rag/

用法（务必先停止服务）：

  .\\.venv\\Scripts\\python.exe project_init.py
  .\\.venv\\Scripts\\python.exe project_init.py -y   # 跳过确认

完成后可再执行 .\\start.ps1。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, settings


# 相对 data/ 删除的业务目录（整目录重建为空）
_PURGE_DIRS = (
    "uploads",  # 应用仓库 / MDM 包等
    "rag",  # 知识库上传、LightRAG 向量、侧车
)

# data/ 下 SQLite 主库及 WAL 附属文件
_DB_GLOBS = (
    "mdm.db",
    "mdm.db-wal",
    "mdm.db-shm",
    "mdm.db-journal",
)


def _rm_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=False)
        print(f"  [del] 目录 {path.relative_to(DATA_DIR)}")
    else:
        path.unlink(missing_ok=True)
        try:
            rel = path.relative_to(DATA_DIR)
        except ValueError:
            rel = path
        print(f"  [del] 文件 {rel}")


def purge_runtime_data() -> None:
    """删除业务落地文件与数据库文件；保留 RSA 密钥。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[1/3] 清理 data 业务文件（根目录 {DATA_DIR}）…")

    for name in _PURGE_DIRS:
        _rm_path(DATA_DIR / name)

    for pattern in _DB_GLOBS:
        for p in DATA_DIR.glob(pattern):
            _rm_path(p)

    # 保险：若配置指向了非默认库名，也尝试删掉 URL 里的文件
    url = (settings.database_url or "").strip()
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///") :]
        # Windows：sqlite:///E:/... 或 sqlite:////E:/...
        db_path = Path(raw)
        if not db_path.is_absolute() and raw.startswith("/"):
            # sqlite:////C:/foo → /C:/foo
            db_path = Path(raw[1:]) if len(raw) > 2 and raw[2] == ":" else Path(raw)
        try:
            if db_path.is_file() and db_path.resolve() != (DATA_DIR / "mdm.db").resolve():
                _rm_path(db_path)
                for suffix in ("-wal", "-shm", "-journal"):
                    side = Path(str(db_path) + suffix)
                    if side.is_file():
                        _rm_path(side)
        except OSError as exc:
            print(f"  [warn] 删除自定义库失败: {exc}")

    print("  [keep] data/rsa_*.pem（若存在）")


def reinit_database() -> None:
    """删库后按首次启动逻辑建表并写入 admin + 系统角色。"""
    print("[2/3] 重建数据库并写入系统种子…")
    # 此时再 import engine，避免清理前占用 SQLite 文件
    from app.bootstrap import init_db
    from app.database import SessionLocal, engine
    from app.services.log_config_service import ensure_config

    engine.dispose()
    init_db()

    db = SessionLocal()
    try:
        ensure_config(db)
        db.commit()
        print("  [ok] 系统日志保留配置已确保存在")
    finally:
        db.close()

    print(f"  [ok] 管理员 {settings.default_admin_username} 已确保存在（密码见文档）")


def ensure_empty_dirs() -> None:
    """恢复知识库等空目录，避免首次上传缺目录。"""
    print("[3/3] 恢复空目录…")
    try:
        from app.rag.paths import ensure_rag_dirs

        ensure_rag_dirs()
        print("  [ok] data/rag/ 空目录已就绪")
    except Exception as exc:
        print(f"  [warn] 创建 rag 目录失败: {exc}")
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    print("  [ok] data/uploads/ 空目录已就绪")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清空业务数据，恢复为刚初始化完成的项目状态"
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="跳过确认提示",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("项目初始化（将删除业务数据与本地库，不可恢复）")
    print("=" * 60)
    print("将删除：data/mdm.db*、data/uploads/、data/rag/")
    print("将保留：data/rsa_*.pem；执行后写入 admin + 系统角色")
    print("请确认服务已停止（start.ps1 / run.py 已 Ctrl+C）。")
    print()

    if not args.yes:
        ans = input("确认执行？输入 yes 继续：").strip().lower()
        if ans != "yes":
            print("已取消。")
            return 1

    try:
        purge_runtime_data()
        reinit_database()
        ensure_empty_dirs()
    except Exception as exc:
        print(f"[fail] 初始化失败: {exc}")
        raise

    print()
    print("=" * 60)
    print("[done] 项目已恢复为初始状态。可执行 .\\start.ps1 启动服务。")
    print(f"登录：{settings.default_admin_username} / 12345678（首次种子；改密后不被覆盖）")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
