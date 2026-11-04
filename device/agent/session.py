"""设备模拟会话：MQTT 订阅 + 策略拉取/上报 + 防抖."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from device.agent import cloud_api, local_apply
from device.agent.log_store import logs
from device.agent.mqtt_config import load_mqtt_config
from device.config import settings
from device.database import SessionLocal, init_schema

logger = logging.getLogger("device.sim")

TOPIC_TEMPLATE = "mdm/{sn}/release"


class DeviceSession:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.sn: str | None = None
        self.connected = False
        self.mqtt_connected = False
        self.mqtt_broker = ""
        self.topic = ""
        self.last_error = ""
        self._client: mqtt.Client | None = None
        self._last_pull_at = 0.0
        self._worker_lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sn": self.sn,
                "connected": self.connected,
                "mqtt_connected": self.mqtt_connected,
                "mqtt_broker": self.mqtt_broker,
                "topic": self.topic,
                "last_error": self.last_error,
                "cloud_base_url": settings.cloud_base_url,
                "pull_debounce_seconds": settings.pull_debounce_seconds,
            }

    def connect(self, sn: str) -> dict[str, Any]:
        sn = (sn or "").strip()
        if not sn:
            raise ValueError("请输入设备 SN")
        with self._lock:
            if self.connected:
                raise RuntimeError("已有设备在线，请先退出再切换 SN")

        logs.clear()
        init_schema()
        cfg = load_mqtt_config()

        with self._lock:
            self.sn = sn
            self.last_error = ""
            self.topic = TOPIC_TEMPLATE.format(sn=sn)
            self.mqtt_broker = f"{cfg['host']}:{cfg['port']}"
            self.connected = True

        logs.add(
            kind="SYS",
            title="开始连接",
            detail={"sn": sn, "topic": self.topic},
        )
        logs.add(
            kind="MQTT",
            title="读取 Broker 配置",
            detail={
                "host": cfg["host"],
                "port": cfg["port"],
                "source": cfg.get("source"),
                "topic": self.topic,
            },
        )

        try:
            self._start_mqtt(cfg, sn)
        except Exception:
            self.disconnect()
            raise

        # 连接后主动拉一次策略并上报
        threading.Thread(
            target=self._safe_pull_and_report,
            kwargs={"reason": "startup"},
            daemon=True,
            name="sim-startup-pull",
        ).start()

        return self.status()

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            sn = self.sn
            client = self._client
            self._client = None
            self.connected = False
            self.mqtt_connected = False
            self.sn = None
            self.topic = ""
            self.mqtt_broker = ""
            self._last_pull_at = 0.0

        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.warning("MQTT disconnect: %s", exc)

        logs.add(kind="SYS", title="已退出设备", detail={"sn": sn})
        return self.status()

    def _start_mqtt(self, cfg: dict[str, Any], sn: str) -> None:
        # 端侧约定：Client ID 直接使用设备 SN
        client_id = (sn or "").strip()[:120]
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            clean_session=bool(cfg.get("clean_session", True)),
        )
        if cfg.get("username"):
            client.username_pw_set(cfg["username"], cfg.get("password") or "")
        elif cfg.get("password"):
            client.username_pw_set("", cfg.get("password") or "")

        topic = self.topic
        qos = int(cfg.get("qos") or 1)

        def on_connect(client, _userdata, _flags, reason_code, _properties=None):
            rc = int(getattr(reason_code, "value", reason_code) or 0)
            ok = rc == 0
            with self._lock:
                self.mqtt_connected = ok
                if not ok:
                    self.last_error = f"MQTT 连接失败 rc={rc}"
            if ok:
                client.subscribe(topic, qos=qos)
                logs.add(
                    kind="MQTT",
                    title="已连接并订阅",
                    detail={"broker": self.mqtt_broker, "topic": topic, "qos": qos},
                )
            else:
                logs.add(
                    kind="MQTT",
                    title="连接失败",
                    detail={"broker": self.mqtt_broker, "rc": rc},
                )

        def on_disconnect(client, _userdata, _flags, reason_code, _properties=None):
            with self._lock:
                self.mqtt_connected = False
            logs.add(
                kind="MQTT",
                title="连接断开",
                detail={"rc": str(reason_code)},
            )

        def on_message(client, _userdata, msg):
            raw = ""
            try:
                raw = msg.payload.decode("utf-8", errors="replace")
            except Exception:
                raw = str(msg.payload)
            logs.add(
                kind="MQTT",
                title="收到消息",
                detail={"topic": msg.topic, "payload": raw, "qos": msg.qos},
            )
            self._handle_mqtt_payload(raw)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        self._client = client
        try:
            client.connect(
                cfg["host"],
                int(cfg["port"]),
                keepalive=int(cfg.get("keep_alive") or 60),
            )
            client.loop_start()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.last_error = str(exc)
                self.mqtt_connected = False
            logs.add(
                kind="MQTT",
                title="连接异常",
                detail={"error": str(exc), "broker": self.mqtt_broker},
            )
            raise

    def _handle_mqtt_payload(self, raw: str) -> None:
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        msg_type = str((data or {}).get("type") or "").strip()

        if msg_type == "STRATEGY_PULL":
            threading.Thread(
                target=self._safe_pull_and_report,
                kwargs={"reason": "STRATEGY_PULL"},
                daemon=True,
            ).start()
        elif msg_type == "SNAPSHOT_REPORT":
            threading.Thread(
                target=self._safe_report_only,
                kwargs={"reason": "SNAPSHOT_REPORT"},
                daemon=True,
            ).start()
        elif msg_type == "DEVICE_CONTROL":
            logs.add(
                kind="CTRL",
                title="设备控制（仅日志）",
                detail={
                    "type": msg_type,
                    "controlType": data.get("controlType"),
                    "payload": data,
                    "note": "模拟器不执行真实控制",
                },
            )
        elif msg_type == "DEVICE_UNBINDING":
            logs.add(
                kind="MQTT",
                title="解绑通知",
                detail={"payload": data, "note": "模拟器仅记录，不自动退出"},
            )
        else:
            logs.add(
                kind="MQTT",
                title=f"未处理类型 {msg_type or '(空)'}",
                detail={"payload": data or raw},
            )

    def _debounce_ok(self) -> bool:
        now = time.time()
        gap = float(settings.pull_debounce_seconds)
        with self._lock:
            if now - self._last_pull_at < gap:
                remain = gap - (now - self._last_pull_at)
                return False
            self._last_pull_at = now
            return True

    def _safe_pull_and_report(self, *, reason: str) -> None:
        if not self._worker_lock.acquire(blocking=False):
            logs.add(
                kind="SYS",
                title="拉取跳过（忙）",
                detail={"reason": reason},
            )
            return
        try:
            if not self._debounce_ok():
                logs.add(
                    kind="SYS",
                    title="拉取跳过（15s 防抖）",
                    detail={
                        "reason": reason,
                        "debounce_seconds": settings.pull_debounce_seconds,
                    },
                )
                return
            sn = self.sn
            if not sn:
                return
            data = cloud_api.get_strategy(sn)
            snapshot = data.get("snapshot") if isinstance(data, dict) else []
            if not isinstance(snapshot, list):
                snapshot = []

            db = SessionLocal()
            try:
                local_stats = local_apply.apply_pulled_snapshot(db, sn, snapshot)
                logs.add(
                    kind="LOCAL",
                    title="本地已执行策略（模拟库）",
                    detail={"reason": reason, "stats": local_stats},
                )
                snap, apps = local_apply.build_report_payload(db, sn)
            finally:
                db.close()

            cloud_api.report_snapshot(
                sn,
                snapshot=snap,
                app_infos=apps,
                device_info=local_apply.default_device_info(sn),
            )
            logs.add(
                kind="SYS",
                title="拉取并上报完成",
                detail={"reason": reason, "snapshot_count": len(snap), "apps": len(apps)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("pull_and_report failed")
            with self._lock:
                self.last_error = str(exc)
            logs.add(
                kind="SYS",
                title="拉取/上报失败",
                detail={"reason": reason, "error": str(exc)},
            )
        finally:
            self._worker_lock.release()

    def _safe_report_only(self, *, reason: str) -> None:
        if not self._worker_lock.acquire(blocking=False):
            logs.add(kind="SYS", title="上报跳过（忙）", detail={"reason": reason})
            return
        try:
            sn = self.sn
            if not sn:
                return
            db = SessionLocal()
            try:
                snap, apps = local_apply.build_report_payload(db, sn)
            finally:
                db.close()
            cloud_api.report_snapshot(
                sn,
                snapshot=snap,
                app_infos=apps,
                device_info=local_apply.default_device_info(sn),
            )
            logs.add(
                kind="SYS",
                title="快照上报完成",
                detail={"reason": reason, "snapshot_count": len(snap), "apps": len(apps)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("report_only failed")
            with self._lock:
                self.last_error = str(exc)
            logs.add(
                kind="SYS",
                title="快照上报失败",
                detail={"reason": reason, "error": str(exc)},
            )
        finally:
            self._worker_lock.release()


session = DeviceSession()
