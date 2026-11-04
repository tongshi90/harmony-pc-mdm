"""业务卡片 · 企业上报 Schema（与企业对接通构 JSON，camelCase）."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BizCardApprovalIn(BaseModel):
    step: int = Field(..., ge=1, description="第几级，从 1 开始")
    handlerId: str = Field(..., min_length=1, max_length=64, description="该级审批人工号")
    status: str = Field(..., min_length=1, max_length=16, description="节点状态")
    handleUrl: str | None = Field(None, max_length=512, description="该级处理地址")
    occurTime: str | None = Field(None, description="该级待办产生时间 ISO8601")
    finishTime: str | None = Field(None, description="该级处理完成时间 ISO8601")
    rejectReason: str | None = Field(None, max_length=512, description="驳回理由")


class BizCardReportIn(BaseModel):
    """企业上报整单状态（全量，非增量）."""

    bizId: str = Field(..., min_length=1, max_length=64, description="企业申请唯一 ID")
    title: str = Field(..., min_length=1, max_length=128, description="单据类型标题")
    content: str = Field(..., min_length=1, max_length=512, description="申请事由")
    applicantId: str = Field(..., min_length=1, max_length=64, description="提交人工号")
    submitTime: str = Field(..., min_length=1, description="提交时间 ISO8601")
    overallStatus: str = Field(..., min_length=1, max_length=16, description="整单状态")
    currentStep: int | None = Field(None, ge=1, description="当前第几级")
    totalStep: int = Field(..., ge=1, description="总审批级数")
    currentHandlerId: str | None = Field(None, max_length=64, description="当前待处理人工号")
    handleUrl: str | None = Field(None, max_length=512, description="当前处理跳转地址")
    approvals: list[BizCardApprovalIn] = Field(..., min_length=1, description="审批节点列表")

    def to_raw_dict(self) -> dict[str, Any]:
        """转为普通 dict，供 source → service 解耦传递（与 JSON 同构）."""
        return self.model_dump(mode="python")
