"""人员管理 CRUD（/platform/member）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.member import MemberCreate, MemberUpdate
from app.services import department_service, member_import_service, member_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.MEMBER))])


@router.get("/groups")
def list_group_options(
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    """人员表单用的分组树（只读，复用成员分组数据）."""
    return ok(department_service.list_departments(db, keyword))


@router.get("/import/template")
@audit_log(module="人员管理", action="下载成员导入模板")
def download_import_template(
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    """下载人员导入 Excel 模板."""
    content = member_import_service.build_import_template_bytes()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="member-import-template.xlsx"'
        },
    )


@router.post("/import")
@audit_log(module="人员管理", action="导入成员")
async def import_members(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    """批量导入成员（仅新增）。部分失败时 data 含失败行 Excel（base64）."""
    return ok(await member_import_service.import_members(db, file))


@router.get("")
def list_members(
    keyword: str | None = Query(None),
    department_id: int | None = Query(None),
    bind: str | None = Query(None, description="bound|unbound"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    return ok(
        member_service.list_members(
            db,
            keyword=keyword,
            department_id=department_id,
            bind=bind,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{member_id}")
def get_member(
    member_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    return ok(member_service.get_member(db, member_id))


@router.post("")
@audit_log(module="人员管理", action="录入成员")
def create_member(
    body: MemberCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    return ok(member_service.create_member(db, body))


@router.put("/{member_id}")
@audit_log(module="人员管理", action="编辑成员")
def update_member(
    member_id: int,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    return ok(member_service.update_member(db, member_id, body))


@router.delete("/{member_id}")
@audit_log(module="人员管理", action="删除成员")
def delete_member(
    member_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER)),
):
    member_service.delete_member(db, member_id)
    return ok(True)
