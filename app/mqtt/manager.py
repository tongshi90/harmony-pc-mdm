"""MQTT Broker 长连接管理.

- 有有效配置（host 非空）时建立长连接；失败自动退避重试，断线自动重连
- 探测连接（test_connect）为一次性短连，不影响长连接实例
- 所有后台连接异常仅记日志，不向外抛出，避免拖垮服务启动
"""

from __future__ import annotations

import logging
import ssl
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger("mdm.mqtt")

# 长连接重试 / 重连退避（秒）
_RETRY_MIN = 2
_RETRY_MAX = 60
# 探测连接超时
_TEST_TIMEOUT = 8.0


@dataclass(frozen=True)
class MqttConnParams:
    host: str
    port: int
    tls: bool = False
    username: str | None = None
    password: str | None = None
    client_id_prefix: str = "mdm-"
    keep_alive: int = 60
    clean_session: bool = True

    @property
    def usable(self) -> bool:
        return bool((self.host or "").strip())

    def fingerprint(self) -> str:
        """用于判断配置是否变化（含密码）."""
        return "|".join(
            [
                self.host.strip(),
                str(self.port),
                "1" if self.tls else "0",
                self.username or "",
                self.password or "",
                self.client_id_prefix or "",
                str(self.keep_alive),
                "1" if self.clean_session else "0",
            ]
        )


def params_from_mapping(data: dict[str, Any]) -> MqttConnParams:
    return MqttConnParams(
        host=str(data.get("host") or "").strip(),
        port=int(data.get("port") or 1883),
        tls=bool(int(data.get("tls") or 0)),
        username=(str(data.get("username") or "").strip() or None),
        password=(str(data.get("password") or "").strip() or None)
        if data.get("password") is not None
        else None,
        client_id_prefix=str(data.get("client_id_prefix") or "mdm-").strip() or "mdm-",
        keep_alive=int(data.get("keep_alive") or 60),
        clean_session=bool(int(data.get("clean_session") if data.get("clean_session") is not None else 1)),
    )


def _make_client(params: MqttConnParams, *, suffix: str) -> mqtt.Client:
    prefix = (params.client_id_prefix or "mdm-").strip() or "mdm-"
    client_id = f"{prefix}{suffix}"[:120]
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
        clean_session=params.clean_session,
    )
    if params.username:
        client.username_pw_set(params.username, params.password or "")
    elif params.password:
        client.username_pw_set("", params.password)
    if params.tls:
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    return client


class MqttManager:
    """进程内单例：维护一条到 Broker 的后台长连接."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._params: MqttConnParams | None = None
        self._client: mqtt.Client | None = None
        self._loop_running = False
        self._connected = False
        self._last_error: str = ""
        self._stopped = False
        # 后台守护线程：在未连上时周期性重试
        self._worker: threading.Thread | None = None
        self._wake = threading.Event()

    # ---------- 对外状态 ----------
    def status(self) -> dict[str, Any]:
        with self._lock:
            p = self._params
            return {
                "connected": self._connected,
                "enabled": bool(p and p.usable),
                "host": p.host if p else "",
                "port": p.port if p else None,
                "last_error": self._last_error or "",
            }

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def publish(
        self,
        topic: str,
        payload: str | bytes,
        qos: int = 1,
        *,
        retain: bool = False,
    ) -> tuple[bool, str]:
        """通过当前长连接发布消息；未连接时返回失败.

        retain=True 时 Broker 会保留该 Topic 最后一条消息，订阅端稍后上线仍可收到。
        """
        topic = (topic or "").strip()
        if not topic:
            return False, "请填写 Topic"
        if qos not in (0, 1, 2):
            qos = 1
        with self._lock:
            client = self._client
            connected = self._connected
            last_err = self._last_error
        if client is None or not connected:
            tip = last_err or "MQTT 未连接"
            return False, f"无法发送：{tip}（请先在平台基础管理中配置并连通 MQTT）"
        try:
            data = payload if isinstance(payload, (bytes, bytearray)) else str(payload or "")
            info = client.publish(topic, data, qos=qos, retain=bool(retain))
            # wait_for_publish 在部分 QoS/版本下可能阻塞；设超时
            try:
                info.wait_for_publish(timeout=5.0)
            except Exception:  # noqa: BLE001
                pass
            if getattr(info, "rc", 0) not in (0, mqtt.MQTT_ERR_SUCCESS):
                return False, f"发布失败（rc={info.rc}）"
            return True, "发送成功"
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT 发布异常 topic=%s: %s", topic, exc)
            return False, f"发布异常：{exc}"

    # ---------- 启动 / 应用配置 ----------
    def start_background(self, params: MqttConnParams | None) -> None:
        """应用配置并确保后台 worker 在跑。永不抛出到调用方."""
        try:
            if params is None or not params.usable:
                self.stop()
                return
            self.apply(params)
        except Exception:  # noqa: BLE001
            logger.exception("MQTT 启动调度异常（已忽略，不影响服务）")

    def apply(self, params: MqttConnParams) -> None:
        """切换到新配置并触发重连（同步返回，连接在后台完成）."""
        if not params.usable:
            self.stop()
            return
        with self._lock:
            self._stopped = False
            same = (
                self._params is not None
                and self._params.fingerprint() == params.fingerprint()
                and self._connected
            )
            self._params = params
            self._last_error = ""
            if same:
                return
            self._teardown_client_locked()
            self._ensure_worker_locked()
            self._wake.set()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._params = None
            self._teardown_client_locked()
            self._connected = False
            self._last_error = ""
            self._wake.set()

    # ---------- 探测连接 ----------
    def test_connect(self, params: MqttConnParams, timeout: float = _TEST_TIMEOUT) -> tuple[bool, str]:
        """一次性探测能否连上 Broker；不影响长连接."""
        if not params.usable:
            return False, "请填写 Broker 地址"
        done = threading.Event()
        result: dict[str, Any] = {"ok": False, "msg": "连接超时"}

        def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
            # VERSION2: reason_code 为 ReasonCode
            try:
                rc = int(reason_code)
            except Exception:  # noqa: BLE001
                rc = getattr(reason_code, "value", 1)
            if rc == 0:
                result["ok"] = True
                result["msg"] = "连接成功"
            else:
                result["ok"] = False
                result["msg"] = f"Broker 拒绝连接（code={rc}）"
            done.set()

        def on_connect_fail(client, userdata):  # noqa: ANN001
            result["ok"] = False
            result["msg"] = "连接失败（网络不可达或被拒绝）"
            done.set()

        client = None
        try:
            client = _make_client(params, suffix=f"probe-{uuid.uuid4().hex[:8]}")
            client.on_connect = on_connect
            if hasattr(client, "on_connect_fail"):
                client.on_connect_fail = on_connect_fail
            client.connect_async(params.host, params.port, keepalive=min(params.keep_alive, 30))
            client.loop_start()
            if not done.wait(timeout):
                result["ok"] = False
                result["msg"] = f"连接超时（{int(timeout)}s 内未响应）"
            return bool(result["ok"]), str(result["msg"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT 探测异常: %s", exc)
            return False, f"连接异常：{exc}"
        finally:
            if client is not None:
                try:
                    client.loop_stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001
                    pass

    # ---------- 内部 ----------
    def _ensure_worker_locked(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._worker_loop, name="mdm-mqtt-worker", daemon=True
        )
        self._worker.start()

    def _teardown_client_locked(self) -> None:
        client = self._client
        self._client = None
        self._loop_running = False
        self._connected = False
        if client is None:
            return
        try:
            client.loop_stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _worker_loop(self) -> None:
        delay = _RETRY_MIN
        while True:
            with self._lock:
                if self._stopped or self._params is None or not self._params.usable:
                    # 空闲等待，直到有新配置
                    self._wake.clear()
                    wait_idle = True
                else:
                    wait_idle = False
                    params = self._params
                    need_connect = not self._connected or self._client is None

            if wait_idle:
                self._wake.wait(timeout=30)
                delay = _RETRY_MIN
                continue

            if need_connect:
                ok = self._try_open(params)
                if ok:
                    delay = _RETRY_MIN
                    # 已连上：等待断线唤醒或配置变更
                    self._wake.clear()
                    self._wake.wait(timeout=30)
                    continue
                logger.warning("MQTT 连接失败，%ss 后重试：%s", delay, self._last_error)
                self._wake.clear()
                self._wake.wait(timeout=delay)
                delay = min(delay * 2, _RETRY_MAX)
            else:
                self._wake.clear()
                self._wake.wait(timeout=30)

    def _try_open(self, params: MqttConnParams) -> bool:
        with self._lock:
            self._teardown_client_locked()
            connected_evt = threading.Event()
            state: dict[str, Any] = {"ok": False, "err": ""}

            def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
                try:
                    rc = int(reason_code)
                except Exception:  # noqa: BLE001
                    rc = getattr(reason_code, "value", 1)
                if rc == 0:
                    with self._lock:
                        self._connected = True
                        self._last_error = ""
                    state["ok"] = True
                else:
                    msg = f"Broker 拒绝连接（code={rc}）"
                    with self._lock:
                        self._connected = False
                        self._last_error = msg
                    state["err"] = msg
                    logger.warning("MQTT 连接被拒 %s:%s code=%s", params.host, params.port, rc)
                connected_evt.set()

            def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):  # noqa: ANN001
                with self._lock:
                    was = self._connected
                    self._connected = False
                    if self._stopped:
                        return
                    try:
                        rc = int(reason_code)
                    except Exception:  # noqa: BLE001
                        rc = getattr(reason_code, "value", -1)
                    self._last_error = f"连接断开（code={rc}）"
                    if was:
                        logger.warning("MQTT 断开 %s:%s code=%s，将自动重连", params.host, params.port, rc)
                self._wake.set()

            try:
                client = _make_client(params, suffix=f"cloud-{uuid.uuid4().hex[:10]}")
                client.reconnect_delay_set(min_delay=_RETRY_MIN, max_delay=_RETRY_MAX)
                client.on_connect = on_connect
                client.on_disconnect = on_disconnect
                client.connect_async(params.host, params.port, keepalive=params.keep_alive)
                client.loop_start()
                self._client = client
                self._loop_running = True
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.warning("MQTT 发起连接异常: %s", exc)
                return False

        # 短等首连结果；失败也保留 loop，由 paho 重连 + worker 唤醒
        connected_evt.wait(timeout=8.0)
        with self._lock:
            if self._connected:
                return True
            if not self._last_error:
                self._last_error = state.get("err") or "连接超时或失败"
            # 若首连失败，拆掉后由 worker 退避重试（避免多个失败 client 堆积）
            if not self._connected:
                self._teardown_client_locked()
            return self._connected


mqtt_manager = MqttManager()
