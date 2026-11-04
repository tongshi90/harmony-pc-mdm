"""人员批量导入（仅新增；失败行返回 Excel）."""

from __future__ import annotations

import base64
import io
import re
from collections import Counter
from typing import Any

from fastapi import HTTPException, UploadFile
from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from app.models.department import SysDepartment, SysMember
from app.utils.security import hash_password
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

# 模板 / 导入表头（顺序固定）
IMPORT_HEADERS = ("姓名", "工号", "账号", "密码", "分组")
FAIL_HEADERS = (*IMPORT_HEADERS, "失败原因")

_HEADER_ALIASES: dict[str, str] = {
    "姓名": "姓名",
    "name": "姓名",
    "工号": "工号",
    "employee_id": "工号",
    "employeeid": "工号",
    "账号": "账号",
    "account": "账号",
    "用户名": "账号",
    "密码": "密码",
    "password": "密码",
    "分组": "分组",
    "分组名": "分组",
    "部门": "分组",
    "department": "分组",
    "group": "分组",
}


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm_header(value: Any) -> str:
    text = re.sub(r"\s+", "", _cell_str(value))
    if text in _HEADER_ALIASES:
        return _HEADER_ALIASES[text]
    low = text.lower()
    if low in _HEADER_ALIASES:
        return _HEADER_ALIASES[low]
    return text


def build_import_template_bytes() -> bytes:
    """生成导入模板 xlsx（含表头与一行示例）."""
    wb = Workbook()
    ws = wb.active
    ws.title = "人员导入"
    ws.append(list(IMPORT_HEADERS))
    ws.append(["张三", "E20260001", "zhangsan", "Abc@1234", "研发中心"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_fail_excel(rows: list[dict[str, str]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "导入失败"
    ws.append(list(FAIL_HEADERS))
    for r in rows:
        ws.append(
            [
                r.get("姓名", ""),
                r.get("工号", ""),
                r.get("账号", ""),
                r.get("密码", ""),
                r.get("分组", ""),
                r.get("失败原因", ""),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _parse_workbook(file_bytes: bytes) -> list[dict[str, str]]:
    """解析 xlsx → 行字典列表；格式错误抛 400."""
    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="文件格式不正确，请上传 .xlsx 模板文件"
        ) from exc

    ws = wb.active
    if ws is None:
        raise HTTPException(status_code=400, detail="导入表格为空，未找到工作表")

    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail="导入表格为空") from exc

    headers = [_norm_header(c) for c in header_row]
    # 去掉尾部空列
    while headers and not headers[-1]:
        headers.pop()
    if not headers or all(not h for h in headers):
        raise HTTPException(status_code=400, detail="导入表格缺少表头")

    missing = [h for h in IMPORT_HEADERS if h not in headers]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"表头不正确，缺少列：{'、'.join(missing)}（需要：{'、'.join(IMPORT_HEADERS)}）",
        )

    col_index = {h: headers.index(h) for h in IMPORT_HEADERS}
    records: list[dict[str, str]] = []
    for raw in rows_iter:
        if raw is None:
            continue
        values = list(raw)
        # 整行空跳过
        if all(_cell_str(v) == "" for v in values):
            continue
        rec = {
            key: _cell_str(values[idx] if idx < len(values) else "")
            for key, idx in col_index.items()
        }
        records.append(rec)

    if not records:
        raise HTTPException(status_code=400, detail="导入表格中没有人员数据")
    return records


def _dept_name_map(db: Session) -> dict[str, SysDepartment | None]:
    """分组名 → 部门；若重名则值为 None（表示歧义）."""
    out: dict[str, SysDepartment | None] = {}
    for d in db.query(SysDepartment).all():
        name = (d.name or "").strip()
        if not name:
            continue
        if name in out:
            out[name] = None
        else:
            out[name] = d
    return out


async def import_members(db: Session, file: UploadFile) -> dict[str, Any]:
    """仅新增导入：成功落库，失败行生成可下载 Excel（base64）."""
    filename = (file.filename or "").strip().lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的 Excel 文件")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="导入文件为空")

    records = _parse_workbook(raw)
    dept_map = _dept_name_map(db)

    # 表内工号 / 账号重复 → 相关行全部失败
    emp_counter = Counter((r["工号"] for r in records if r["工号"]))
    acc_counter = Counter((r["账号"] for r in records if r["账号"]))
    dup_emps = {k for k, n in emp_counter.items() if n > 1}
    dup_accs = {k for k, n in acc_counter.items() if n > 1}

    existing_emps = {
        r[0]
        for r in db.query(SysMember.employee_id)
        .filter(SysMember.is_delete == 0)
        .all()
    }
    existing_accs = {
        r[0]
        for r in db.query(SysMember.account).filter(SysMember.is_delete == 0).all()
    }

    ok_rows: list[dict[str, Any]] = []
    fail_rows: list[dict[str, str]] = []

    for rec in records:
        name = rec["姓名"]
        employee_id = rec["工号"]
        account = rec["账号"]
        password = rec["密码"]
        group_name = rec["分组"]
        reasons: list[str] = []

        if not name:
            reasons.append("姓名不能为空")
        if not employee_id:
            reasons.append("工号不能为空")
        if not account:
            reasons.append("账号不能为空")
        if not password:
            reasons.append("密码不能为空")
        if not group_name:
            reasons.append("分组不能为空")

        if employee_id and employee_id in dup_emps:
            reasons.append("表格内工号重复")
        if account and account in dup_accs:
            reasons.append("表格内账号重复")

        if employee_id and employee_id in existing_emps:
            reasons.append("工号已存在")
        if account and account in existing_accs:
            reasons.append("账号已存在")

        dept: SysDepartment | None = None
        if group_name:
            if group_name not in dept_map:
                reasons.append("分组不存在")
            else:
                dept = dept_map[group_name]
                if dept is None:
                    reasons.append("分组名称在系统中不唯一，请先处理重名分组")

        if reasons:
            fail_rows.append({**rec, "失败原因": "；".join(reasons)})
            continue

        assert dept is not None
        ok_rows.append(
            {
                "name": name,
                "employee_id": employee_id,
                "account": account,
                "password": password,
                "department_id": dept.id,
            }
        )

    ts = local_now()
    for item in ok_rows:
        db.add(
            SysMember(
                id=snowflake_id(),
                department_id=item["department_id"],
                name=item["name"],
                employee_id=item["employee_id"],
                account=item["account"],
                password=hash_password(item["password"]),
                status=1,
                is_delete=0,
                create_time=ts,
                update_time=ts,
            )
        )
    if ok_rows:
        db.commit()

    result: dict[str, Any] = {
        "success_count": len(ok_rows),
        "fail_count": len(fail_rows),
        "total": len(records),
    }
    if fail_rows:
        fail_bytes = _build_fail_excel(fail_rows)
        result["fail_file_name"] = "member-import-failures.xlsx"
        result["fail_file_base64"] = base64.b64encode(fail_bytes).decode("ascii")
    return result
