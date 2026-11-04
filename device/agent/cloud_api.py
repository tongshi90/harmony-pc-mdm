"""调用云侧设备接口（HTTP），不写云侧数据库."""

from __future__ import annotations

from typing import Any

import requests

from device.agent.log_store import logs
from device.config import settings


def _url(path: str) -> str:
    base = settings.cloud_base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def get_strategy(sn: str) -> dict[str, Any]:
    """GET /api/strategy/get"""
    path = "/api/strategy/get"
    params = {"SN": sn}
    url = _url(path)
    try:
        resp = requests.get(url, params=params, timeout=30)
        body: Any
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        ok = resp.status_code == 200 and isinstance(body, dict) and body.get("code") == 0
        logs.add(
            kind="API",
            title="拉取策略",
            api_path=path,
            detail={
                "method": "GET",
                "url": url,
                "params": params,
                "status_code": resp.status_code,
                "response": body,
                "ok": ok,
            },
        )
        if not ok:
            msg = ""
            if isinstance(body, dict):
                msg = body.get("message") or body.get("detail") or ""
            raise RuntimeError(msg or f"strategy/get 失败 HTTP {resp.status_code}")
        return body.get("data") or {}
    except requests.RequestException as exc:
        logs.add(
            kind="API",
            title="拉取策略失败",
            api_path=path,
            detail={"method": "GET", "url": url, "params": params, "error": str(exc)},
        )
        raise


def report_snapshot(
    sn: str,
    *,
    snapshot: list[dict[str, Any]],
    app_infos: list[dict[str, str]],
    device_info: dict[str, Any] | None,
) -> dict[str, Any]:
    """POST /api/report/snapshot"""
    path = "/api/report/snapshot"
    url = _url(path)
    payload = {
        "SN": sn,
        "snapshot": snapshot,
        "appInfos": app_infos,
    }
    if device_info:
        payload["deviceInfo"] = device_info
    try:
        resp = requests.post(url, json=payload, timeout=60)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        ok = resp.status_code == 200 and isinstance(body, dict) and body.get("code") == 0
        logs.add(
            kind="API",
            title="上报快照",
            api_path=path,
            detail={
                "method": "POST",
                "url": url,
                "request": payload,
                "status_code": resp.status_code,
                "response": body,
                "ok": ok,
            },
        )
        if not ok:
            msg = ""
            if isinstance(body, dict):
                msg = body.get("message") or body.get("detail") or ""
            raise RuntimeError(msg or f"report/snapshot 失败 HTTP {resp.status_code}")
        return body.get("data") or {}
    except requests.RequestException as exc:
        logs.add(
            kind="API",
            title="上报快照失败",
            api_path=path,
            detail={
                "method": "POST",
                "url": url,
                "request": payload,
                "error": str(exc),
            },
        )
        raise
