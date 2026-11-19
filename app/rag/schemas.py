"""RAG 管理台请求/响应模型."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)


class RagChunkUpdate(BaseModel):
    """管理台编辑单条切片正文；保存后重新 Embedding。"""

    text: str = Field(..., min_length=1, max_length=100000, description="切片正文")


class ConversationMessage(BaseModel):
    """P3-2：上送的近几轮对话（不含当前 question）。"""

    role: Literal["user", "assistant"] = Field(..., description="user=提问 / assistant=回答")
    content: str = Field(..., min_length=1, max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    # 可选：限定某个知识库；不传则检索全部知识库
    kb_id: int | str | None = None
    top_k: int = Field(5, ge=1, le=20)
    # P1-3：默认开启 SiliconFlow Rerank；调试页可关闭对比
    enable_rerank: bool = True
    # P3-2：近几轮历史，供 P3-1 检索前改写；不传则按当前句检索
    conversation_history: list[ConversationMessage] | None = None


class DeviceAskRequest(BaseModel):
    """设备侧问答（/api/rag/ask）：SN + 问题必填；sessionId 可空表示新会话。"""

    question: str = Field(..., min_length=1, max_length=4000)
    sn: str | None = Field(None, max_length=128, description="设备 SN")
    SN: str | None = Field(None, max_length=128, description="设备 SN（协议字段）")
    # 设备协议统一用驼峰 sessionId（与 SN 等字段风格一致）
    sessionId: str | int | None = Field(
        None, description="会话 ID；空或不传=新会话"
    )

    def resolved_sn(self) -> str:
        return (self.sn or self.SN or "").strip()

    def resolved_session_id(self) -> str:
        if self.sessionId is None:
            return ""
        return str(self.sessionId).strip()
