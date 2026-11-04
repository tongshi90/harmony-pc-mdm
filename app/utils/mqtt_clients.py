"""查询 EMQX 当前已连接的 MQTT client_id（设备 SN）列表.

规则：
  - 业务 MQTT 连通性仍用 t_sys_mqtt_config
  - 管理 API 地址 / 账号 / 密码一律用 config.py（Settings / MDM_ 环境变量）
  - 鉴权：Dashboard 账号密码 → POST /api/v5/login → Bearer Token
    （不用 HTTP Basic：EMQX 会把 Basic 当成 api_key/api_secret）
  - 查询类接口不向外抛异常；需要区分「失败」与「零在线」时用 query_connected_clients()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.mqtt.manager import mqtt_manager
from app.services.mqtt_service import load_conn_params

logger = logging.getLogger("mdm.mqtt.clients")

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]


@dataclass
class ClientsQueryResult:
    """EMQX clients 查询结果."""

    ok: bool
    client_ids: list[str] = field(default_factory=list)
    message: str = ""


def _resolve_api_endpoint(mqtt_host: str, tls: bool) -> tuple[str, str, str, str]:
    """返回 (api_base, host, username, password)；账号密码来自 Settings，host 可回落业务 MQTT."""
    host = (settings.mqtt_api_host or "").strip() or (mqtt_host or "").strip()
    port = int(settings.mqtt_api_port or 18083)
    username = (settings.mqtt_api_username or "").strip()
    password = str(settings.mqtt_api_password or "")
    scheme = "https" if tls else "http"
    api_base = f"{scheme}://{host}:{port}" if host else ""
    return api_base, host, username, password


def _login_bearer(
    session: "requests.Session", base: str, username: str, password: str
) -> tuple[str | None, str]:
    """Dashboard 账号密码登录，返回 (token, error_message)."""
    url = f"{base.rstrip('/')}/api/v5/login"
    try:
        resp = session.post(
            url,
            json={"username": username, "password": password},
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"EMQX 登录请求异常: {exc}"

    if resp.status_code >= 400:
        body = (resp.text or "")[:200]
        return None, f"EMQX 账号密码登录失败 HTTP {resp.status_code}: {body}"

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None, "EMQX 登录响应不是 JSON"

    token = data.get("token") or data.get("access_token")
    if not token:
        return None, "EMQX 登录成功但未返回 token"
    return str(token), ""


def _fetch_client_ids_via_api(
    *,
    api_base: str,
    username: str,
    password: str,
    page_size: int = 1000,
) -> ClientsQueryResult:
    if requests is None:
        return ClientsQueryResult(ok=False, message="未安装 requests，无法查询 EMQX clients")

    if not username:
        return ClientsQueryResult(ok=False, message="未配置 mqtt_api_username（config.py）")

    base = api_base.rstrip("/")
    url = f"{base}/api/v5/clients"
    limit = max(1, min(int(page_size), 10000))
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    # 仅账号密码登录拿 Bearer；禁止 Basic Auth（会触发 BAD_API_KEY_OR_SECRET）
    token, login_err = _login_bearer(session, base, username, password)
    if not token:
        logger.warning(login_err)
        return ClientsQueryResult(ok=False, message=login_err)

    headers = {"Authorization": f"Bearer {token}"}

    use_conn_state = False
    probe = session.get(
        url,
        params={"page": 1, "limit": 1, "conn_state": "connected"},
        headers=headers,
        timeout=30,
    )
    if probe.status_code == 200:
        use_conn_state = True
    elif probe.status_code == 401:
        msg = f"EMQX 管理 API Token 无效: {(probe.text or '')[:200]}"
        logger.warning(msg)
        return ClientsQueryResult(ok=False, message=msg)
    elif probe.status_code >= 400:
        probe2 = session.get(
            url,
            params={"page": 1, "limit": 1},
            headers=headers,
            timeout=30,
        )
        if probe2.status_code == 401:
            msg = f"EMQX 管理 API Token 无效: {(probe2.text or '')[:200]}"
            logger.warning(msg)
            return ClientsQueryResult(ok=False, message=msg)
        if probe2.status_code >= 400:
            msg = (
                f"EMQX 管理 API 查询失败 HTTP {probe2.status_code}: "
                f"{(probe2.text or '')[:200]}"
            )
            logger.warning(msg)
            return ClientsQueryResult(ok=False, message=msg)

    client_ids: list[str] = []
    seen: set[str] = set()
    page = 1
    while True:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if use_conn_state:
            params["conn_state"] = "connected"
        resp = session.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code >= 400:
            msg = (
                f"EMQX 管理 API 分页失败 HTTP {resp.status_code}: "
                f"{(resp.text or '')[:200]}"
            )
            logger.warning(msg)
            return ClientsQueryResult(ok=False, message=msg)

        payload = resp.json()
        batch = payload.get("data") or []
        if not isinstance(batch, list):
            return ClientsQueryResult(ok=False, message="EMQX 响应 data 不是数组")

        for item in batch:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("clientid") or "").strip()
            if not cid or cid in seen:
                continue
            connected = item.get("connected")
            conn_state = str(item.get("conn_state") or "").lower()
            if use_conn_state:
                is_online = True
            elif connected is True or conn_state in ("connected", "idle"):
                is_online = True
            elif connected is False or conn_state == "disconnected":
                is_online = False
            else:
                is_online = True
            if not is_online:
                continue
            seen.add(cid)
            client_ids.append(cid)

        meta = payload.get("meta") or {}
        hasnext = meta.get("hasnext")
        count = meta.get("count")
        if hasnext is True:
            page += 1
        elif hasnext is False:
            break
        elif count is not None and page * limit >= int(count):
            break
        elif len(batch) < limit:
            break
        else:
            page += 1
        if not batch or page > 10000:
            break

    return ClientsQueryResult(
        ok=True,
        client_ids=client_ids,
        message=f"已连接 {len(client_ids)} 个 client",
    )


def query_connected_clients(db: Session | None = None) -> ClientsQueryResult:
    """查询已连接 client_id；用 ok 区分失败与「零在线」."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        params = load_conn_params(db)
        if params is None or not params.usable:
            return ClientsQueryResult(ok=False, message="MQTT 未配置（host 为空）")

        try:
            ok, message = mqtt_manager.test_connect(params)
        except Exception as exc:  # noqa: BLE001
            logger.exception("MQTT 连接探测异常")
            return ClientsQueryResult(ok=False, message=f"MQTT 连接探测异常: {exc}")
        if not ok:
            return ClientsQueryResult(
                ok=False, message=f"MQTT 无法连接: {message or 'unknown'}"
            )

        api_base, api_host, api_user, api_pass = _resolve_api_endpoint(
            params.host, params.tls
        )
        if not api_host:
            return ClientsQueryResult(
                ok=False, message="管理 API host 未配置（mqtt_api_host / MQTT host）"
            )

        try:
            return _fetch_client_ids_via_api(
                api_base=api_base,
                username=api_user,
                password=api_pass,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("查询 EMQX clients 失败")
            return ClientsQueryResult(ok=False, message=f"查询 EMQX clients 失败: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("query_connected_clients 失败")
        return ClientsQueryResult(ok=False, message=str(exc) or "查询失败")
    finally:
        if own_session and db is not None:
            db.close()


def list_connected_client_ids(db: Session | None = None) -> list[str]:
    """返回已连接 client_id 列表；失败时返回 []（不区分失败与零在线）."""
    result = query_connected_clients(db)
    return list(result.client_ids) if result.ok else []
