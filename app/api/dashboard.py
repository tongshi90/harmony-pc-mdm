"""数据看板（/platform/dashboard）."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.services import dashboard_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.DASHBOARD))])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DASHBOARD)),
):
    return ok(dashboard_service.get_overview(db))
