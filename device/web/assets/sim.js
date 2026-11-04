(function () {
  const $ = (id) => document.getElementById(id);
  const connectPanel = $("connect-panel");
  const logPanel = $("log-panel");
  const btnExit = $("btn-exit");
  const statusLine = $("status-line");
  const connectErr = $("connect-err");
  const logBody = $("log-body");
  const mask = $("detail-mask");

  let pollTimer = null;

  async function api(path, opts) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    let body;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    if (!res.ok) {
      const msg =
        (body && (body.detail || body.message)) ||
        `HTTP ${res.status}`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    if (body && body.code !== 0 && body.code !== undefined) {
      throw new Error(body.message || "请求失败");
    }
    return body ? body.data : null;
  }

  function renderStatus(st) {
    if (!st || !st.connected) {
      statusLine.textContent = "未连接 · 请输入 SN 开始模拟";
      connectPanel.style.display = "";
      logPanel.style.display = "none";
      btnExit.style.display = "none";
      return;
    }
    const mqtt = st.mqtt_connected ? "MQTT 已连接" : "MQTT 连接中/断开";
    statusLine.textContent = `SN ${st.sn} · ${mqtt} · ${st.mqtt_broker || "-"} · ${st.topic} · 云侧 ${st.cloud_base_url}`;
    connectPanel.style.display = "none";
    logPanel.style.display = "";
    btnExit.style.display = "";
  }

  function renderLogs(rows) {
    if (!rows || !rows.length) {
      logBody.innerHTML = '<tr><td colspan="5" class="mute">暂无记录</td></tr>';
      return;
    }
    logBody.innerHTML = rows
      .map(
        (r) => `<tr>
        <td>${esc(r.time)}</td>
        <td><span class="kind ${esc(r.kind)}">${esc(r.kind)}</span></td>
        <td>${esc(r.title)}</td>
        <td><code>${esc(r.api_path || "-")}</code></td>
        <td><button type="button" class="btn" data-id="${esc(r.id)}">详情</button></td>
      </tr>`
      )
      .join("");
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  async function refresh() {
    try {
      const st = await api("/sim/status");
      renderStatus(st);
      if (st && st.connected) {
        const rows = await api("/sim/logs?limit=200");
        renderLogs(rows);
      }
    } catch (e) {
      statusLine.textContent = e.message || "状态获取失败";
    }
  }

  function startPoll() {
    stopPoll();
    pollTimer = setInterval(refresh, 2000);
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  $("btn-connect").addEventListener("click", async () => {
    connectErr.style.display = "none";
    const sn = ($("sn-input").value || "").trim();
    if (!sn) {
      connectErr.textContent = "请输入 SN";
      connectErr.style.display = "";
      return;
    }
    $("btn-connect").disabled = true;
    try {
      const st = await api("/sim/connect", {
        method: "POST",
        body: JSON.stringify({ sn }),
      });
      renderStatus(st);
      await refresh();
      startPoll();
    } catch (e) {
      connectErr.textContent = e.message || "连接失败";
      connectErr.style.display = "";
    } finally {
      $("btn-connect").disabled = false;
    }
  });

  $("sn-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("btn-connect").click();
  });

  btnExit.addEventListener("click", async () => {
    try {
      await api("/sim/disconnect", { method: "POST" });
    } catch (_) {}
    stopPoll();
    renderStatus(null);
    $("sn-input").value = "";
  });

  $("btn-refresh").addEventListener("click", refresh);

  logBody.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-id]");
    if (!btn) return;
    try {
      const item = await api(`/sim/logs/${btn.dataset.id}`);
      $("detail-title").textContent = `${item.kind} · ${item.title}`;
      $("detail-body").textContent = JSON.stringify(item.detail || {}, null, 2);
      mask.classList.add("show");
    } catch (err) {
      alert(err.message || "加载详情失败");
    }
  });

  $("detail-close").addEventListener("click", () => mask.classList.remove("show"));
  mask.addEventListener("click", (e) => {
    if (e.target === mask) mask.classList.remove("show");
  });

  refresh().then((_) => {
    api("/sim/status").then((st) => {
      if (st && st.connected) startPoll();
    });
  });
})();
