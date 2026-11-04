"""企业对接 OpenAPI · 审批业务卡片上报（/openapi/* 白名单，无需登录）.

本期仅 POST /approval/report；补偿查询、端侧触达见设计文档段落 B。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.biz_card import BizCardReportIn
from app.schemas.common import fail, ok
from app.services import biz_card_source
from app.services.biz_card_service import BizCardValidationError, upsert_biz_card

logger = logging.getLogger("mdm.biz_card")

router = APIRouter(prefix="/approval", tags=["企业对接-业务卡片"])

CODE_VALIDATION = 40001
CODE_SERVER = 50001


@router.post("/report")
@no_audit
async def report_approval(request: Request, db: Session = Depends(get_db)):
    """企业侧上报整单审批状态：校验后拆主表/步骤副表按 bizId 覆盖落库."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=200,
            content=fail("参数校验失败：请求体须为 JSON", code=CODE_VALIDATION),
        )

    try:
        body = BizCardReportIn.model_validate(payload)
    except ValidationError as exc:
        msg = _first_validation_message(exc)
        return JSONResponse(
            status_code=200,
            content=fail(f"参数校验失败：{msg}", code=CODE_VALIDATION),
        )

    try:
        raw = biz_card_source.from_report_body(body)
        biz_id = upsert_biz_card(db, raw, source="REPORT")
        return ok({"bizId": biz_id})
    except BizCardValidationError as exc:
        return JSONResponse(
            status_code=200,
            content=fail(exc.message, code=exc.code),
        )
    except Exception:
        logger.exception("业务卡片上报落库异常")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            status_code=500,
            content=fail("服务端异常", code=CODE_SERVER),
        )


def _first_validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "字段不合法"
    err = errors[0]
    loc = ".".join(str(x) for x in err.get("loc", ()) if x != "body")
    msg = err.get("msg") or "字段不合法"
    return f"{loc} {msg}" if loc else msg
