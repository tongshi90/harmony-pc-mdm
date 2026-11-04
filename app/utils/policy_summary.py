"""策略项摘要：按「核心动作 + 关键配置」生成一句可读文案，入库后列表直接返回."""

from __future__ import annotations

from typing import Any, Callable, Mapping

# 远程操控
_REMOTE_OPS = {
    "lockDevice": "锁定",
    "unlockDevice": "解除锁定",
}

# 定位
_LOCATION = {
    "DEFAULT": "定位由用户自行开关",
    "DISALLOW": "禁止定位",
    "FORCE_OPEN": "强制开启定位",
}

# U 盘
_USB = {
    "READ_WRITE": "U盘设为可读可写",
    "READ_ONLY": "U盘设为只读",
    "DISABLED": "禁用 U盘",
}


def _as_dict(param: Any) -> dict[str, Any]:
    return param if isinstance(param, dict) else {}


def _as_list(val: Any) -> list:
    return val if isinstance(val, list) else []


def _first_app_label(items: list, resolve: Callable[[str], str | None] | None = None) -> str:
    for it in items:
        if isinstance(it, dict):
            for key in ("name", "app_name", "appName", "bundleName", "appId", "id"):
                v = it.get(key)
                if v is not None and str(v).strip():
                    raw = str(v).strip()
                    if resolve and key in ("appId", "bundleName", "id"):
                        return resolve(raw) or raw
                    return raw
        elif it is not None and str(it).strip():
            raw = str(it).strip()
            if resolve:
                return resolve(raw) or raw
            return raw
    return ""


# 密码有效期：管理台按「天」；端侧协议 / 预期快照为毫秒
_MS_PER_DAY = 86_400_000
# 大于此值视为已是毫秒（合理天数远小于此）
_VALIDITY_MS_THRESHOLD = 100_000
_PSW_CODES = frozenset({"PSW_MANAGEMENT", "PASSWORD_POLICY"})
_APP_CONFIG_LIST_KEYS = (
    "allowAppIds",
    "disallowAppIds",
    "disallowedUninstallAppIds",
)


def validity_period_to_ms(raw: Any) -> int | None:
    """将 validityPeriod 规范为毫秒；已是毫秒则原样返回；无效返回 None."""
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > _VALIDITY_MS_THRESHOLD:
        return n
    return n * _MS_PER_DAY


def _normalize_app_ref_list(
    raw: Any,
    *,
    resolve_app_name: Callable[[str], str | None] | None = None,
) -> list[dict[str, str]]:
    """APP_CONFIG 名单：统一为 [{appId, appName}]；兼容历史纯 appId 字符串列表."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for it in _as_list(raw):
        app_id = ""
        app_name = ""
        if isinstance(it, dict):
            app_id = str(it.get("appId") or "").strip()
            app_name = str(it.get("appName") or "").strip()
        elif it is not None:
            app_id = str(it).strip()
        if not app_id or app_id in seen:
            continue
        seen.add(app_id)
        if not app_name and resolve_app_name:
            app_name = (resolve_app_name(app_id) or "").strip()
        if not app_name:
            app_name = app_id
        out.append({"appId": app_id, "appName": app_name})
    return out


def normalize_app_config_ids_only(param: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """合规对比用：只保留各名单的 appId（排序去重），忽略 appName."""
    src = dict(param or {}) if isinstance(param, Mapping) else {}
    out: dict[str, list[str]] = {}
    for key in _APP_CONFIG_LIST_KEYS:
        ids: list[str] = []
        for it in _as_list(src.get(key)):
            if isinstance(it, dict):
                aid = str(it.get("appId") or "").strip()
            else:
                aid = str(it or "").strip()
            if aid:
                ids.append(aid)
        out[key] = sorted(set(ids))
    return out


def normalize_param_for_expected(
    policy_code: str,
    param: Mapping[str, Any] | None,
    *,
    resolve_app_name: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """写入设备预期快照前的 param 规范化.

    - 密码策略 validityPeriod：天 → 毫秒
    - 应用配置管理三名单：统一为 [{appId, appName}]，并尽量补齐应用名
    """
    out = dict(param or {}) if isinstance(param, Mapping) else {}
    code = (policy_code or "").strip()

    if code in _PSW_CODES and "validityPeriod" in out:
        ms = validity_period_to_ms(out.get("validityPeriod"))
        if ms is None:
            out.pop("validityPeriod", None)
        else:
            out["validityPeriod"] = ms
        return out

    if code == "APP_CONFIG_MANAGEMENT":
        for key in _APP_CONFIG_LIST_KEYS:
            out[key] = _normalize_app_ref_list(
                out.get(key), resolve_app_name=resolve_app_name
            )
        return out

    return out


def _validity_days(param: dict[str, Any]) -> int | None:
    raw = param.get("validityPeriod")
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    # 表单按天；协议/预期快照为毫秒（> 10 万视为毫秒）
    if n > _VALIDITY_MS_THRESHOLD:
        return max(1, n // _MS_PER_DAY)
    return n


def build_policy_item_summary(
    policy_code: str,
    param: Mapping[str, Any] | None = None,
    *,
    resolve_app_name: Callable[[str], str | None] | None = None,
) -> str:
    """根据 policy_code + param 生成单条策略摘要."""
    code = (policy_code or "").strip()
    p = _as_dict(param)

    if code == "WIFI_SET":
        ssid = str(p.get("ssid") or "").strip()
        return f"连接「{ssid}」Wifi" if ssid else "清空 Wifi 的自动连接"

    if code == "REMOTE_CONTROL":
        op = str(p.get("operationType") or "").strip()
        label = _REMOTE_OPS.get(op)
        return f"对设备执行{label}" if label else "清空远程操控指令"

    if code == "LOCATION_POLICY":
        t = str(p.get("policyType") or "").strip()
        return _LOCATION.get(t) or "清空定位限制"

    if code == "APP_MANAGEMENT":
        installs = _as_list(p.get("currentApps"))
        uninstalls = _as_list(p.get("uninstallApps"))
        n, u = len(installs), len(uninstalls)
        if n == 0 and u == 0:
            return "清空静默安装和卸载"
        parts: list[str] = []
        if n:
            name = _first_app_label(installs, resolve_app_name)
            if n == 1 and name:
                parts.append(f"安装「{name}」应用")
            elif name:
                parts.append(f"安装「{name}」等{n}个应用")
            else:
                parts.append(f"安装{n}个应用")
        if u:
            name = _first_app_label(uninstalls, resolve_app_name)
            if u == 1 and name:
                parts.append(f"卸载「{name}」应用")
            elif name:
                parts.append(f"卸载「{name}」等{u}个应用")
            else:
                parts.append(f"卸载{u}个应用")
        if n and u:
            # 「安装…，并卸载…」
            return f"{parts[0]}，并{parts[1]}"
        return parts[0] if parts else "清空静默安装和卸载"

    if code == "APP_CONFIG_MANAGEMENT":
        allow = _as_list(p.get("allowAppIds"))
        disallow = _as_list(p.get("disallowAppIds"))
        ban = _as_list(p.get("disallowedUninstallAppIds"))
        a, d, f = len(allow), len(disallow), len(ban)
        if a == 0 and d == 0 and f == 0:
            return "清空应用安装与卸载限制"
        return f"允许安装{a}个、禁止安装{d}个、禁止卸载{f}个应用"

    if code == "DOMAIN_MANAGEMENT":
        domains = [str(x).strip() for x in _as_list(p.get("domainNames")) if str(x).strip()]
        n = len(domains)
        if n == 0:
            return "清空网站访问限制"
        if n == 1:
            return f"禁止访问「{domains[0]}」"
        return f"禁止访问「{domains[0]}」等{n}个网站"

    if code == "FIREWALL_MANAGEMENT":
        rules = _as_list(p.get("firewalls"))
        n = len(rules)
        if n == 0:
            return "清空防火墙规则"
        return f"设置 {n} 条防火墙拦截规则"

    if code in ("PSW_MANAGEMENT", "PASSWORD_POLICY"):
        days = _validity_days(p)
        desc = str(p.get("additionalDescription") or "").strip()
        regex = str(p.get("complexityRegex") or "").strip()
        if days is not None:
            return f"开机密码有效期 {days} 天"
        if desc:
            short = desc if len(desc) <= 20 else desc[:20] + "…"
            return f"开机密码要求：{short}"
        if regex:
            return "已配置开机密码规则"
        return "清空开机密码规则"

    if code == "USB_MANAGEMENT":
        t = str(p.get("usbPolicy") or "").strip()
        return _USB.get(t) or "清空 U盘使用限制"

    # 未知策略：尽量给出一句
    if not p:
        return "已添加策略项"
    return "已配置策略参数"


def aggregate_policy_summaries(summaries: list[str], *, limit: int = 3) -> str:
    """多策略聚合，供任务列表「策略内容」列."""
    cleaned = [s.strip() for s in summaries if s and str(s).strip()]
    if not cleaned:
        return "—"
    if len(cleaned) <= limit:
        return "；".join(cleaned)
    head = "；".join(cleaned[:limit])
    return f"{head}；等{len(cleaned)}项"


def make_app_name_resolver(db) -> Callable[[str], str | None]:
    """按 app_id / bundle_name / 主键解析应用显示名（惰性缓存）."""
    from app.models.app_pkg import AppBase

    cache: dict[str, str | None] = {}

    def resolve(key: str) -> str | None:
        k = str(key or "").strip()
        if not k:
            return None
        if k in cache:
            return cache[k]
        row = (
            db.query(AppBase)
            .filter(
                (AppBase.app_id == k)
                | (AppBase.bundle_name == k)
                | (AppBase.app_code == k)
            )
            .first()
        )
        if row is None:
            try:
                pk = int(k)
            except (TypeError, ValueError):
                pk = None
            if pk is not None:
                row = db.query(AppBase).filter(AppBase.id == pk).first()
        name = (row.app_name if row else None) or None
        cache[k] = name
        return name

    return resolve
