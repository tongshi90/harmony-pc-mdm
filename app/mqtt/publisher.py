"""MQTT 发送通用工具.

业务侧统一调用 ``publish_mqtt(sn, message, qos)``，不要直接操作底层 Client。
实际 Topic 固定为：``mdm/{SN}/release``
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

from app.mqtt.manager import mqtt_manager

logger = logging.getLogger("mdm.mqtt.publish")

# QoS：0 至多一次 · 1 至少一次（默认）· 2 恰好一次
DEFAULT_QOS = 1
TOPIC_TEMPLATE = "mdm/{sn}/release"
# 策略拉取通知等批量发送的默认并发
DEFAULT_MQTT_POOL_WORKERS = 8


def _normalize_qos(qos: int | None) -> int:
    if qos is None:
        return DEFAULT_QOS
    try:
        value = int(qos)
    except (TypeError, ValueError):
        return DEFAULT_QOS
    return value if value in (0, 1, 2) else DEFAULT_QOS


def build_release_topic(sn: str) -> str:
    """由设备 SN 拼接下发 Topic：mdm/{SN}/release."""
    value = (sn or "").strip()
    if not value:
        raise ValueError("请填写设备 SN")
    return TOPIC_TEMPLATE.format(sn=value)


def publish_mqtt(
    sn: str,
    message: str = "",
    qos: int | None = None,
    *,
    retain: bool = False,
) -> dict[str, Any]:
    """向指定设备 SN 对应的 release Topic 发布一条消息.

    Args:
        sn: 设备 SN（必填），实际 Topic 为 ``mdm/{SN}/release``
        message: 消息正文，默认空串
        qos: 0 / 1 / 2；不传或非法时默认 ``1``（至少一次）
        retain: 是否保留消息（数据擦除等需离线可达的指令应设为 True）

    Returns:
        ``{"ok": True, "message": "...", "sn": "...", "topic": "...", "qos": 1, "broker": "..."}``

    Raises:
        ValueError: SN 为空，或当前未连接 / 发布失败
    """
    topic = build_release_topic(sn)
    use_qos = _normalize_qos(qos)
    ok, tip = mqtt_manager.publish(
        topic, message or "", qos=use_qos, retain=bool(retain)
    )
    if not ok:
        raise ValueError(tip)
    st = mqtt_manager.status()
    host = st.get("host") or ""
    port = st.get("port")
    broker = f"{host}:{port}" if host and port is not None else host
    return {
        "ok": True,
        "message": tip,
        "sn": (sn or "").strip(),
        "topic": topic,
        "qos": use_qos,
        "retain": bool(retain),
        "broker": broker,
    }


def publish_mqtt_many(
    sns: Iterable[str],
    message: str = "",
    qos: int | None = None,
    *,
    retain: bool = False,
    max_workers: int = DEFAULT_MQTT_POOL_WORKERS,
) -> dict[str, Any]:
    """向多台设备并行发布同一条消息（有界线程池）.

    单台失败不影响其它设备；返回 notified / failed 及失败 SN 列表。
    空列表时直接返回零计数。
    """
    targets = sorted({str(s).strip() for s in (sns or []) if str(s).strip()})
    if not targets:
        return {"notified": 0, "failed": 0, "failed_sns": []}

    workers = max(1, min(int(max_workers or DEFAULT_MQTT_POOL_WORKERS), len(targets)))
    notified = 0
    failed_sns: list[str] = []

    def _one(sn: str) -> tuple[str, bool, str]:
        try:
            publish_mqtt(sn=sn, message=message, qos=qos, retain=retain)
            return sn, True, ""
        except Exception as exc:  # noqa: BLE001
            return sn, False, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, sn) for sn in targets]
        for fut in as_completed(futures):
            sn, ok, err = fut.result()
            if ok:
                notified += 1
            else:
                failed_sns.append(sn)
                logger.warning("批量 MQTT 失败 sn=%s: %s", sn, err)

    return {
        "notified": notified,
        "failed": len(failed_sns),
        "failed_sns": failed_sns,
    }
