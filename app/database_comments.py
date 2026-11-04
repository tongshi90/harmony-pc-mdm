"""SQLite 建表时把 Column.comment 写入 DDL（/* ... */）.

SQLite 不支持 MySQL 式 COMMENT 子句，但会把完整 CREATE 文本存进 sqlite_master；
在列定义后追加块注释后，DB 工具查看表 DDL 即可看到字段含义 / 枚举说明。

用法：在 mapped_column(..., comment="...") 上写说明即可；本模块在 database 导入时注册。
注意：仅对新 create_all 创建的表生效；已有表需删表重建后才会出现在 DDL 中。
"""

from __future__ import annotations

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateColumn


def _safe_block_comment(text: str) -> str:
    """避免 comment 内出现 */ 打断 DDL."""
    return (text or "").replace("*/", "* /").replace("\n", " ").strip()


@compiles(CreateColumn, "sqlite")
def _sqlite_create_column_with_comment(element, compiler, **kw):  # noqa: ANN001
    text = compiler.visit_create_column(element, **kw)
    comment = getattr(element.element, "comment", None)
    if comment:
        text = f"{text} /* {_safe_block_comment(str(comment))} */"
    return text
