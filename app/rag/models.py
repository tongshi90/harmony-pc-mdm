"""RAG 元数据表（与 MDM 业务表同库 mdm.db；向量在 Chroma）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RagKnowledgeBase(Base):
    """知识库分组 t_rag_knowledge_base（仅便于文件管理；问答默认可跨库检索）."""

    __tablename__ = "t_rag_knowledge_base"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RagFile(Base):
    """知识库文件 t_rag_file."""

    __tablename__ = "t_rag_file"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # parsing / completed / failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="parsing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 正式开始解析的时间（排队等待不计；超时兜底以此为准；空=尚未被 worker 领取）
    parse_start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RagAskSession(Base):
    """设备侧问答会话 t_rag_ask_session（管理台调试不落库）."""

    __tablename__ = "t_rag_ask_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sn: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RagAskMessage(Base):
    """设备侧问答消息 t_rag_ask_message."""

    __tablename__ = "t_rag_ask_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # user | assistant
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
