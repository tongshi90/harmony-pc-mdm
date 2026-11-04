"""设备策略快照：读写与预期/当前差异对比."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.app_pkg import AppBase, AppVersion
from app.models.device import Device, DeviceAppInstalled
from app.models.device_snapshot import DevicePolicyCurrent, DevicePolicyExpected
from app.utils.policy_summary import (
    make_app_name_resolver,
    normalize_app_config_ids_only,
    normalize_param_for_expected,
)
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

# 不走「预期表 vs 当前表」对比的策略（有独立对比逻辑）
COMPARE_SPECIAL_POLICY_CODES = frozenset(
    {
        "APP_MANAGEMENT",  # 预期 vs t_device_app_installed
    }
)

# 兼容旧字段名：完全不参与任何对比的策略（当前为空）
COMPARE_EXCLUDE_POLICY_CODES = frozenset()

# 按策略忽略的 param 字段（仅表对表对比）
COMPARE_IGNORE_PARAM_KEYS: dict[str, frozenset[str]] = {
    "WIFI_SET": frozenset({"certEntry"}),
}

# 组装协议 snapshot 时：仅 WIFI_SET 使用 commandCode，其余 sceneCode
_COMMAND_CODE_POLICIES = frozenset({"WIFI_SET"})


def protocol_key_of(policy_code: str) -> str:
    return "commandCode" if policy_code in _COMMAND_CODE_POLICIES else "sceneCode"


def _parse_param(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dumps_param(param: dict[str, Any] | None) -> str:
    return json.dumps(param or {}, ensure_ascii=False, separators=(",", ":"))


def _item_out(row: DevicePolicyExpected | DevicePolicyCurrent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "device_sn": row.device_sn,
        "policy_code": row.policy_code,
        "param": _parse_param(row.param_json),
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else None,
    }


def _strip_ignored_keys(
    param: dict[str, Any], ignore_keys: frozenset[str] | None
) -> dict[str, Any]:
    if not ignore_keys:
        return dict(param or {})
    return {k: v for k, v in (param or {}).items() if k not in ignore_keys}


def _sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _semantic_normalize(value: Any) -> Any | None:
    """语义归一：未设置 → None；标量转字符串；列表无序；空对象/空列表视为未设置.

    未设置包括：null、缺字段、""（trim 后空）、[]、归一后无有效键的 {}。
    缺行与「有行但全空」在外层都按 param={} 再归一，结果同为 None/{}。
    """
    if value is None:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            nv = _semantic_normalize(v)
            if nv is None:
                continue
            out[str(k)] = nv
        return out if out else None
    if isinstance(value, list):
        items: list[Any] = []
        for v in value:
            nv = _semantic_normalize(v)
            if nv is None:
                continue
            items.append(nv)
        if not items:
            return None
        return sorted(items, key=_sort_key)
    # 数字 / 布尔 / 其它：统一转字符串再比（业务保证两侧格式一致）
    text = str(value).strip()
    return text if text else None


def _normalize_param_for_compare(
    param: dict[str, Any] | None,
    *,
    ignore_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    raw = _strip_ignored_keys(param or {}, ignore_keys)
    normalized = _semantic_normalize(raw)
    return normalized if isinstance(normalized, dict) else {}


def params_equal(
    policy_code: str, expected: dict[str, Any] | None, current: dict[str, Any] | None
) -> bool:
    code = (policy_code or "").strip()
    # 应用配置：仅按 appId 比对，避免 appName 文案差异导致误判不合规
    if code == "APP_CONFIG_MANAGEMENT":
        return normalize_app_config_ids_only(expected) == normalize_app_config_ids_only(
            current
        )
    ignore = COMPARE_IGNORE_PARAM_KEYS.get(code, frozenset())
    # 先按端侧形态归一（如密码有效期天→毫秒），再语义对比
    exp = normalize_param_for_expected(code, expected)
    cur = normalize_param_for_expected(code, current)
    left = _normalize_param_for_compare(exp, ignore_keys=ignore)
    right = _normalize_param_for_compare(cur, ignore_keys=ignore)
    return left == right


def _diff_normalized(
    expected: Any,
    current: Any,
    path: str = "",
) -> list[dict[str, Any]]:
    """对已语义归一的结构生成字段差异（仅不一致的路径）."""
    diffs: list[dict[str, Any]] = []

    if isinstance(expected, dict) and isinstance(current, dict):
        keys = set(expected.keys()) | set(current.keys())
        for key in sorted(keys):
            child = f"{path}.{key}" if path else key
            if key not in expected:
                diffs.append(
                    {"path": child, "expected": None, "current": current.get(key)}
                )
            elif key not in current:
                diffs.append(
                    {"path": child, "expected": expected.get(key), "current": None}
                )
            else:
                diffs.extend(
                    _diff_normalized(expected[key], current[key], child)
                )
        return diffs

    if isinstance(expected, list) and isinstance(current, list):
        # 列表已按值排序；按多重集合匹配，只报对不上的元素
        pool = list(current)
        for i, exp_item in enumerate(expected):
            found = -1
            for j, cur_item in enumerate(pool):
                if cur_item == exp_item:
                    found = j
                    break
            child = f"{path}[{i}]" if path else f"[{i}]"
            if found < 0:
                diffs.append({"path": child, "expected": exp_item, "current": None})
            else:
                pool.pop(found)
        for j, cur_item in enumerate(pool):
            child = f"{path}[+{j}]" if path else f"[+{j}]"
            diffs.append({"path": child, "expected": None, "current": cur_item})
        return diffs

    if expected != current:
        diffs.append(
            {"path": path or "$", "expected": expected, "current": current}
        )
    return diffs


def diff_params(
    policy_code: str,
    expected: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    code = (policy_code or "").strip()
    if code == "APP_CONFIG_MANAGEMENT":
        left = normalize_app_config_ids_only(expected)
        right = normalize_app_config_ids_only(current)
        return _diff_normalized(left, right, "")
    ignore = COMPARE_IGNORE_PARAM_KEYS.get(code, frozenset())
    exp = normalize_param_for_expected(code, expected)
    cur = normalize_param_for_expected(code, current)
    left = _normalize_param_for_compare(exp, ignore_keys=ignore)
    right = _normalize_param_for_compare(cur, ignore_keys=ignore)
    return _diff_normalized(left, right, "")


def list_expected(db: Session, device_sn: str) -> list[dict[str, Any]]:
    sn = (device_sn or "").strip()
    rows = (
        db.query(DevicePolicyExpected)
        .filter(DevicePolicyExpected.device_sn == sn)
        .order_by(DevicePolicyExpected.policy_code.asc())
        .all()
    )
    return [_item_out(r) for r in rows]


def list_current(db: Session, device_sn: str) -> list[dict[str, Any]]:
    sn = (device_sn or "").strip()
    rows = (
        db.query(DevicePolicyCurrent)
        .filter(DevicePolicyCurrent.device_sn == sn)
        .order_by(DevicePolicyCurrent.policy_code.asc())
        .all()
    )
    return [_item_out(r) for r in rows]


def upsert_expected(
    db: Session,
    *,
    device_sn: str,
    policy_code: str,
    param: dict[str, Any] | None,
    commit: bool = True,
) -> dict[str, Any]:
    """写入/覆盖单条预期策略.

    commit=False 时仅写入会话，供策略下发等同事务场景复用。
    - 密码策略 validityPeriod：管理台为天，此处换算为毫秒再入库
    - 应用配置管理：名单规范为 [{appId, appName}]，并按仓库补齐应用名
    """
    sn = (device_sn or "").strip()
    code = (policy_code or "").strip()
    now = local_now()
    resolve = make_app_name_resolver(db) if code == "APP_CONFIG_MANAGEMENT" else None
    normalized = normalize_param_for_expected(
        code, param, resolve_app_name=resolve
    )
    row = (
        db.query(DevicePolicyExpected)
        .filter(DevicePolicyExpected.device_sn == sn, DevicePolicyExpected.policy_code == code)
        .first()
    )
    if not row:
        row = DevicePolicyExpected(
            id=snowflake_id(),
            device_sn=sn,
            policy_code=code,
            create_time=now,
        )
        db.add(row)
    row.param_json = _dumps_param(normalized)
    row.update_time = now
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return _item_out(row)


def _version_key(value: Any) -> tuple:
    """将版本字符串拆成可比较的数字元组；无法解析时回落字符串."""
    text = str(value or "").strip()
    if not text:
        return (0,)
    if text.isdigit():
        return (int(text),)
    parts: list[int] = []
    buf = ""
    for ch in text:
        if ch.isdigit():
            buf += ch
        elif buf:
            parts.append(int(buf))
            buf = ""
    if buf:
        parts.append(int(buf))
    return tuple(parts) if parts else (0, text)


def _cmp_version(left: Any, right: Any) -> int:
    a, b = _version_key(left), _version_key(right)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _empty_app_management_param() -> dict[str, Any]:
    return {"currentApps": [], "uninstallApps": []}


def _ensure_app_management_shape(param: dict[str, Any] | None) -> dict[str, Any]:
    """规范化 APP_MANAGEMENT param；丢弃已废弃的 totalApps."""
    base = _empty_app_management_param()
    if not isinstance(param, dict):
        return base
    current = param.get("currentApps")
    uninstall = param.get("uninstallApps")
    base["currentApps"] = [x for x in current if isinstance(x, dict)] if isinstance(current, list) else []
    if isinstance(uninstall, list):
        base["uninstallApps"] = [str(x).strip() for x in uninstall if str(x).strip()]
    else:
        base["uninstallApps"] = []
    return base


def _app_entry_match(entry: dict[str, Any], *, app_id: str, bundle_name: str) -> bool:
    eid = str(entry.get("appId") or "").strip()
    ebundle = str(entry.get("bundleName") or "").strip()
    if app_id and eid and eid == app_id:
        return True
    if bundle_name and ebundle and ebundle == bundle_name:
        return True
    return False


def merge_app_management_install(
    existing: dict[str, Any] | None,
    *,
    app_entry: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """按批量安装规则合并 APP_MANAGEMENT 预期.

    返回 (新 param, 动作): skipped | updated | added
    """
    param = _ensure_app_management_shape(existing)
    app_id = str(app_entry.get("appId") or "").strip()
    bundle_name = str(app_entry.get("bundleName") or "").strip()
    new_ver = str(app_entry.get("version") or "").strip()

    # 安装时从卸载名单移除同应用，避免冲突
    if bundle_name:
        param["uninstallApps"] = [
            x for x in param["uninstallApps"] if x != bundle_name
        ]

    for idx, entry in enumerate(param["currentApps"]):
        if not _app_entry_match(entry, app_id=app_id, bundle_name=bundle_name):
            continue
        old_ver = str(entry.get("version") or "").strip()
        if _cmp_version(old_ver, new_ver) >= 0:
            return param, "skipped"
        merged = dict(entry)
        merged.update(
            {
                "appId": app_id or merged.get("appId") or "",
                "bundleName": bundle_name or merged.get("bundleName") or "",
                "version": new_ver,
                "bundleDownloadUrl": str(app_entry.get("bundleDownloadUrl") or ""),
            }
        )
        param["currentApps"][idx] = merged
        return param, "updated"

    param["currentApps"].append(
        {
            "appId": app_id,
            "bundleName": bundle_name,
            "version": new_ver,
            "bundleDownloadUrl": str(app_entry.get("bundleDownloadUrl") or ""),
        }
    )
    return param, "added"


def merge_app_management_uninstall(
    existing: dict[str, Any] | None,
    *,
    bundle_name: str,
) -> tuple[dict[str, Any], str]:
    """按批量卸载规则合并 APP_MANAGEMENT 预期.

    返回 (新 param, 动作): skipped | added
    """
    param = _ensure_app_management_shape(existing)
    bundle = (bundle_name or "").strip()
    if not bundle:
        return param, "skipped"

    if bundle in param["uninstallApps"]:
        return param, "skipped"

    # 卸载时从安装名单移除同应用
    param["currentApps"] = [
        e
        for e in param["currentApps"]
        if str(e.get("bundleName") or "").strip() != bundle
    ]
    param["uninstallApps"].append(bundle)
    return param, "added"


def get_expected_param(db: Session, device_sn: str, policy_code: str) -> dict[str, Any]:
    sn = (device_sn or "").strip()
    code = (policy_code or "").strip()
    row = (
        db.query(DevicePolicyExpected)
        .filter(DevicePolicyExpected.device_sn == sn, DevicePolicyExpected.policy_code == code)
        .first()
    )
    return _parse_param(row.param_json if row else None)


def replace_current_snapshot(
    db: Session,
    *,
    device_sn: str,
    items: list[dict[str, Any]],
    skip_codes: frozenset[str] | None = None,
    commit: bool = True,
) -> list[dict[str, Any]]:
    """设备上报：按全量 items 替换该设备当前快照.

    未出现在 items 中的策略类型会从当前快照表删除（全量覆盖）。
    items 元素：{"policy_code":"WIFI_SET","param":{...}}
    也可直接传协议形态：{"commandCode"|"sceneCode":"...","param":{...}}
    skip_codes：跳过写入的策略码（如 APP_MANAGEMENT，由已装应用分析）。
    """
    sn = (device_sn or "").strip()
    now = local_now()
    skip = skip_codes or frozenset()
    db.query(DevicePolicyCurrent).filter(DevicePolicyCurrent.device_sn == sn).delete()

    # 同码多次上报时保留最后一次
    pending: dict[str, dict[str, Any]] = {}
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        policy_code = str(
            raw.get("policy_code")
            or raw.get("commandCode")
            or raw.get("sceneCode")
            or ""
        ).strip()
        if not policy_code or policy_code in skip:
            continue
        param = raw.get("param") if isinstance(raw.get("param"), dict) else {}
        pending[policy_code] = param

    out_rows: list[DevicePolicyCurrent] = []
    for policy_code, param in pending.items():
        row = DevicePolicyCurrent(
            id=snowflake_id(),
            device_sn=sn,
            policy_code=policy_code,
            param_json=_dumps_param(param),
            create_time=now,
            update_time=now,
        )
        db.add(row)
        out_rows.append(row)
    if commit:
        db.commit()
    else:
        db.flush()
    return [_item_out(r) for r in out_rows]


def _load_installed_apps_for_sn(db: Session, device_sn: str) -> list[dict[str, Any]]:
    """设备已安装应用（协议字段 + 版本），按 SN 查询."""
    sn = (device_sn or "").strip()
    device = db.query(Device).filter(Device.sn == sn).first()
    if not device:
        return []
    rows = (
        db.query(DeviceAppInstalled, AppBase, AppVersion)
        .join(AppBase, AppBase.id == DeviceAppInstalled.app_id)
        .join(AppVersion, AppVersion.id == DeviceAppInstalled.app_version_id)
        .filter(DeviceAppInstalled.device_id == device.id)
        .all()
    )
    out: list[dict[str, Any]] = []
    for _inst, app, ver in rows:
        out.append(
            {
                "appId": (app.app_id or "").strip(),
                "bundleName": (app.bundle_name or "").strip(),
                "version": (ver.version_name or "").strip(),
                "versionCode": (ver.version_code or "").strip(),
                "appName": app.app_name or "",
            }
        )
    return out


def _find_installed(
    installed: list[dict[str, Any]], *, app_id: str, bundle_name: str
) -> dict[str, Any] | None:
    for row in installed:
        if app_id and row.get("appId") and row["appId"] == app_id:
            return row
        if bundle_name and row.get("bundleName") and row["bundleName"] == bundle_name:
            return row
    return None


def _compare_app_management_vs_installed(
    expected_param: dict[str, Any],
    installed: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """APP_MANAGEMENT：预期快照 vs 设备已安装应用表.

    - 需安装：设备须已装该应用且版本 >= 预期版本
    - 需卸载：设备上不得仍存在该应用
    全部满足返回 None；否则返回 diffs 项。
    """
    param = _ensure_app_management_shape(expected_param)
    field_diffs: list[dict[str, Any]] = []

    for idx, entry in enumerate(param["currentApps"]):
        app_id = str(entry.get("appId") or "").strip()
        bundle = str(entry.get("bundleName") or "").strip()
        need_ver = str(entry.get("version") or "").strip()
        path = f"currentApps[{idx}]"
        hit = _find_installed(installed, app_id=app_id, bundle_name=bundle)
        if not hit:
            field_diffs.append(
                {
                    "path": path,
                    "expected": entry,
                    "current": None,
                    "message": "设备未安装该应用或版本不足",
                }
            )
            continue
        # 预期 param.version 为 version_name，与已安装版本的 version_name 比较
        actual_ver = str(hit.get("version") or "").strip()
        if _cmp_version(actual_ver, need_ver) < 0:
            field_diffs.append(
                {
                    "path": f"{path}.version",
                    "expected": need_ver,
                    "current": actual_ver,
                    "message": "已安装版本低于预期",
                }
            )

    for idx, bundle in enumerate(param["uninstallApps"]):
        bundle = str(bundle or "").strip()
        if not bundle:
            continue
        hit = _find_installed(installed, app_id="", bundle_name=bundle)
        if hit:
            field_diffs.append(
                {
                    "path": f"uninstallApps[{idx}]",
                    "expected": None,
                    "current": {
                        "bundleName": hit.get("bundleName"),
                        "version": hit.get("version"),
                    },
                    "message": "预期卸载但设备仍已安装",
                }
            )

    if not field_diffs:
        return None
    return {
        "policy_code": "APP_MANAGEMENT",
        "status": "mismatch",
        "message": "应用安装/卸载与预期不符",
        "expected_param": param,
        "current_param": {
            "installedApps": installed,
        },
        "field_diffs": field_diffs,
    }


def refresh_device_compliance(
    db: Session,
    device_sn: str,
    *,
    commit: bool = False,
) -> bool:
    """根据预期/当前快照（及 APP_MANAGEMENT vs 已装应用）重算合规字段.

    写回 t_device.is_compliant 与 policy_diff_count（= diffs 条数，同终端明细「差异」）。
    返回是否合规（True=合规）。设备不存在时返回 True 且不报错。
    """
    sn = (device_sn or "").strip()
    if not sn:
        return True
    device = db.query(Device).filter(Device.sn == sn).first()
    if not device:
        return True
    cmp = get_device_snapshot_compare(db, sn)
    diffs = cmp.get("diffs") or []
    diff_count = len(diffs) if isinstance(diffs, list) else 0
    ok = bool(cmp.get("consistent")) and diff_count == 0
    device.is_compliant = 1 if ok else 0
    device.policy_diff_count = diff_count
    device.update_time = local_now()
    if commit:
        db.commit()
    else:
        db.flush()
    return ok


def get_device_snapshot_compare(db: Session, device_sn: str) -> dict[str, Any]:
    """按设备 SN 返回预期/当前快照及差异.

    - 一般策略：语义对比（缺行 ≡ 全空；""/null/缺字段/空列表等价；列表无序；标量转字符串）
    - APP_MANAGEMENT：预期 vs t_device_app_installed（版本 ≥ 即匹配）
    - WIFI_SET.certEntry：不参与对比
    """
    sn = (device_sn or "").strip()
    expected_all = list_expected(db, sn)
    current_all = list_current(db, sn)

    # 返回列表：APP_MANAGEMENT 的「当前」不取策略当前表，而用已安装应用合成
    expected = [
        x
        for x in expected_all
        if x["policy_code"] not in COMPARE_EXCLUDE_POLICY_CODES
    ]
    current = [
        x
        for x in current_all
        if x["policy_code"] not in COMPARE_EXCLUDE_POLICY_CODES
        and x["policy_code"] not in COMPARE_SPECIAL_POLICY_CODES
    ]

    installed = _load_installed_apps_for_sn(db, sn)
    app_exp = next(
        (x for x in expected_all if x["policy_code"] == "APP_MANAGEMENT"), None
    )
    if app_exp is not None:
        current.append(
            {
                "id": None,
                "device_sn": sn,
                "policy_code": "APP_MANAGEMENT",
                "param": {"installedApps": installed},
                "create_time": None,
                "update_time": None,
            }
        )

    # 表对表语义对比（跳过 APP_MANAGEMENT）；缺行按空 param
    exp_map = {
        x["policy_code"]: x
        for x in expected
        if x["policy_code"] not in COMPARE_SPECIAL_POLICY_CODES
    }
    cur_map = {
        x["policy_code"]: x
        for x in current
        if x["policy_code"] not in COMPARE_SPECIAL_POLICY_CODES
    }
    codes = sorted(set(exp_map.keys()) | set(cur_map.keys()))

    diffs: list[dict[str, Any]] = []
    for code in codes:
        exp = exp_map.get(code)
        cur = cur_map.get(code)
        exp_param = (exp.get("param") if exp else None) or {}
        cur_param = (cur.get("param") if cur else None) or {}
        if params_equal(code, exp_param, cur_param):
            continue
        field_diffs = diff_params(code, exp_param, cur_param)
        diffs.append(
            {
                "policy_code": code,
                "status": "mismatch",
                "message": "策略配置不一致",
                "expected_param": exp_param,
                "current_param": cur_param,
                "field_diffs": field_diffs,
            }
        )

    # APP_MANAGEMENT：预期 vs 已安装应用
    if app_exp is not None:
        app_diff = _compare_app_management_vs_installed(
            app_exp.get("param") or {}, installed
        )
        if app_diff:
            diffs.append(app_diff)

    return {
        "device_sn": sn,
        "expected": expected,
        "current": current,
        "diffs": diffs,
        "consistent": len(diffs) == 0,
        "excluded_policy_codes": sorted(COMPARE_EXCLUDE_POLICY_CODES),
        "special_compare_policy_codes": sorted(COMPARE_SPECIAL_POLICY_CODES),
    }


def build_expected_snapshot_payload(db: Session, device_sn: str) -> list[dict[str, Any]]:
    """组装设备拉取用的协议 snapshot 列表.

    再次走 normalize，兼容历史：密码有效期按天、应用配置纯 appId 字符串列表等。
    """
    items = list_expected(db, device_sn)
    resolve = make_app_name_resolver(db)
    payload = []
    for it in items:
        code = it["policy_code"]
        param = normalize_param_for_expected(
            code, it.get("param") or {}, resolve_app_name=resolve
        )
        payload.append(
            {
                protocol_key_of(code): code,
                "param": param,
            }
        )
    return payload
