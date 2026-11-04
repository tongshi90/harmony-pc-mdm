/**
 * 设备详情：按 Tab 懒加载（切换时重新拉取最新数据）
 * 注意：MDMLayout.mount 会先 ensureAuth 再写入 DOM，数据加载必须放在 onMount 里。
 */
(async function () {
  const U = MDMUtils;
  const sn = U.query('sn') || '';

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function policyName(code) {
    const c = U.findCommand && U.findCommand(code);
    return (c && c.name) || code;
  }

  function pendingPanel(text) {
    return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(text)}</div></div>`;
  }

  const toolbarLead = `
    <div class="device-detail-lead">
      <h1 class="device-detail-title">设备详情</h1>
      <a class="btn" href="${U.href('devices')}">返回列表</a>
    </div>`;

  if (!sn) {
    MDMLayout.mount({
      pageId: 'device-detail',
      hidePageHead: true,
      content: `
        <div class="device-detail-toolbar">
          ${toolbarLead}
        </div>
        ${pendingPanel('缺少设备 SN 参数')}`
    });
    return;
  }

  MDMLayout.mount({
    pageId: 'device-detail',
    hidePageHead: true,
    content: `
      <div class="device-detail-toolbar">
        ${toolbarLead}
        <div class="detail-actions" id="device-detail-actions">
          <button class="btn" type="button" disabled title="加载中">快照上报</button>
          <button class="btn" type="button" disabled title="加载中">重启</button>
          <button class="btn" type="button" disabled title="加载中">关机</button>
          <button class="btn" type="button" disabled title="加载中">锁屏</button>
          <button class="btn btn-warn" type="button" disabled title="加载中">管理员解绑</button>
        </div>
      </div>
      <div id="tabs-wrap">
        <div class="tabs">
          <div class="tab-item active" data-tab="basic">设备基本信息</div>
          <div class="tab-item" data-tab="snapshot">设备快照</div>
          <div class="tab-item" data-tab="apps">已安装应用</div>
          <div class="tab-item" data-tab="bizcard">业务卡片</div>
          <div class="tab-item" data-tab="track">设备轨迹</div>
        </div>
        <div class="tab-panel active" data-panel="basic" id="panel-basic"><div class="panel"><div class="panel-body text-muted">正在加载基本信息…</div></div></div>
        <div class="tab-panel" data-panel="snapshot" id="panel-snapshot"><div class="panel"><div class="panel-body text-muted">切换到此页时加载</div></div></div>
        <div class="tab-panel" data-panel="apps" id="panel-apps"><div class="panel"><div class="panel-body text-muted">切换到此页时加载</div></div></div>
        <div class="tab-panel" data-panel="bizcard" id="panel-bizcard"><div class="panel"><div class="panel-body text-muted">切换到此页时加载</div></div></div>
        <div class="tab-panel" data-panel="track" id="panel-track"><div class="panel"><div class="panel-body text-muted">切换到此页时加载</div></div></div>
      </div>`,
    async onMount() {
      const tabsWrap = document.getElementById('tabs-wrap');
      const basicPanel = document.getElementById('panel-basic');
      const snapshotPanel = document.getElementById('panel-snapshot');
      const appsPanel = document.getElementById('panel-apps');
      const bizcardPanel = document.getElementById('panel-bizcard');
      const trackPanel = document.getElementById('panel-track');
      const actionsEl = document.getElementById('device-detail-actions');
      let trackPage = 1;
      const trackPageSize = 20;
      let bizKind = 'mine';
      let bizPage = 1;
      const bizPageSize = 20;
      /** 防止快速切 Tab 时旧请求覆盖新结果 */
      const loadSeq = { basic: 0, snapshot: 0, apps: 0, bizcard: 0, track: 0 };

      function canWipe() {
        const u = (window.MDM && MDM.user) || {};
        if (Number(u.is_admin) === 1) return true;
        const code = (u.role_code || u.dept || '').trim();
        return code === 'system_admin';
      }

      async function runControl(deviceSn, controlType, okMessage) {
        try {
          const ret = await MDMApi.controlDevice(deviceSn, controlType);
          if (ret && ret.skipped) {
            U.toast(ret.message || '设备离线，指令未下发', 'error');
            return;
          }
          if (ret && ret.pending) {
            U.toast(ret.message || '指令已缓存，设备上线后将自动下发');
            if (controlType === 'DISK_ERASURE') {
              location.href = U.href('devices');
            }
            return;
          }
          U.toast((ret && ret.message) || okMessage || '指令已下发');
          if (controlType === 'DISK_ERASURE') {
            location.href = U.href('devices');
          }
        } catch (e) {
          U.toast(e.message || '操作失败', 'error');
        }
      }

      function renderHeader(d) {
        if (!actionsEl) return;
        const bound = !!d.bound;
        const boundAttr = bound ? '' : ' disabled title="设备未绑定"';
        const wipeBtn = canWipe()
          ? `<button class="btn btn-danger" type="button" id="btn-disk-erasure"${bound ? ' title="擦除设备全部数据，不可恢复"' : boundAttr}>数据擦除</button>`
          : '';
        actionsEl.innerHTML = `
          <button class="btn" type="button" id="btn-device-report"${bound ? ' title="催设备上报基本信息、已装应用与策略快照"' : boundAttr}>快照上报</button>
          <button class="btn" type="button" id="btn-reboot"${bound ? ' title="远程重启设备"' : boundAttr}>重启</button>
          <button class="btn" type="button" id="btn-shutdown"${bound ? ' title="远程关闭设备"' : boundAttr}>关机</button>
          <button class="btn" type="button" id="btn-lock-screen"${bound ? ' title="远程锁定屏幕"' : boundAttr}>锁屏</button>
          <button class="btn btn-warn" type="button" id="btn-admin-unbind"${bound ? ' title="解除绑定，并清除策略快照与已装应用记录"' : boundAttr}>管理员解绑</button>
          ${wipeBtn}`;
        document.getElementById('btn-admin-unbind')?.addEventListener('click', () => {
          if (!bound) return;
          U.confirm('确认解绑该设备？将清除绑定关系、策略快照与已装应用记录，并向设备下发解绑通知。', async () => {
            try {
              const ret = await MDMApi.unbindDevice(d.sn);
              if (ret && ret.mqtt_notified === false) {
                U.toast('已解绑，但 MQTT 通知失败：' + (ret.mqtt_error || '未知错误'), 'error');
              } else {
                U.toast('已解绑');
              }
              location.href = U.href('devices');
            } catch (e) {
              U.toast(e.message || '解绑失败', 'error');
            }
          });
        });
        document.getElementById('btn-device-report')?.addEventListener('click', () => {
          if (!bound) return;
          requestDeviceReport(d.sn);
        });
        document.getElementById('btn-reboot')?.addEventListener('click', () => {
          U.confirm('确认重启该设备？设备离线时将不会下发该指令。', () => {
            runControl(d.sn, 'reboot', '重启指令已下发');
          });
        });
        document.getElementById('btn-shutdown')?.addEventListener('click', () => {
          U.confirm('确认关闭该设备？设备离线时将不会下发该指令。', () => {
            runControl(d.sn, 'shutDown', '关机指令已下发');
          });
        });
        document.getElementById('btn-lock-screen')?.addEventListener('click', () => {
          U.confirm('确认远程锁屏？设备离线时将不会下发该指令。', () => {
            runControl(d.sn, 'lockScreen', '锁屏指令已下发');
          });
        });
        document.getElementById('btn-disk-erasure')?.addEventListener('click', () => {
          U.modal({
            title: '确认数据擦除',
            okText: '确认擦除',
            body: `
              <p style="margin:0;color:var(--error);font-weight:700;line-height:1.6">
                此操作将解除设备绑定，并擦除设备上的全部数据，且不可撤销，请谨慎确认。
              </p>
              <p class="text-muted" style="margin:12px 0 0;font-size:12px">若设备当前离线，擦除指令将缓存，待其上线后自动下发。</p>`,
            onOk: async () => {
              await runControl(d.sn, 'DISK_ERASURE', '数据擦除指令已下发');
            }
          });
        });
      }

      function renderBasic(d) {
        const bound = !!d.bound;
        const hasBasic = !!d.has_basic_info;
        const notice = !bound
          ? `<div class="panel mb-16"><div class="panel-body text-muted">设备尚未绑定，仅预登记了序列号。</div></div>`
          : (!hasBasic
            ? `<div class="panel mb-16"><div class="panel-body text-muted">已绑定，等待设备首次上报基本信息。</div></div>`
            : '');
        const dash = (v) => (hasBasic ? escapeHtml(v || '—') : '<span class="text-muted">待上报</span>');
        basicPanel.innerHTML = `
          ${notice}
          <div class="grid-2" style="margin-bottom:16px">
            <div class="panel" style="margin:0"><div class="panel-header"><h3>运行与绑定</h3></div><div class="panel-body" style="padding:0"><table class="kv-table"><tbody>
              <tr><th>在线状态</th><td>${bound ? U.badgeStatus(d.status) : '<span class="badge badge-free">未绑定</span>'}</td></tr>
              <tr><th>策略合规</th><td>${bound ? U.badgeStatus(d.compliance || 'compliant') : '<span class="text-muted">—</span>'}</td></tr>
              <tr><th>激活状态</th><td>${d.bind_status === 1 ? '已激活' : '待激活'}</td></tr>
              <tr><th>激活时间</th><td>${escapeHtml(d.activate_time || '—')}</td></tr>
              <tr><th>最后在线</th><td>${escapeHtml(d.online_time || '—')}</td></tr>
              <tr><th>绑定人员</th><td>${bound
                ? `${escapeHtml(d.member_name || '')}${d.employee_id ? '（工号 ' + escapeHtml(d.employee_id) + '）' : ''}`
                : '<span class="text-muted">未绑定</span>'}</td></tr>
              ${bound
                ? `<tr><th>所属分组</th><td>${escapeHtml(d.department_path || '—')}</td></tr>`
                : `<tr><th>所属分组</th><td class="text-muted">绑定员工后随人员分组归属</td></tr>`}
              <tr><th>Agent 版本</th><td>${hasBasic ? escapeHtml(d.agent_version || '—') : '<span class="text-muted">待上报</span>'}</td></tr>
            </tbody></table></div></div>
            <div class="panel" style="margin:0"><div class="panel-header"><h3>设备信息</h3></div><div class="panel-body" style="padding:0"><table class="kv-table"><tbody>
              <tr><th>产品型号</th><td>${dash(d.model)}</td></tr>
              <tr><th>产品版本</th><td>${dash(d.model_version)}</td></tr>
              <tr><th>厂商</th><td>${dash(d.vendor)}</td></tr>
              <tr><th>终端 SN</th><td><code>${escapeHtml(d.sn)}</code></td></tr>
              <tr><th>IMEI</th><td>${dash(d.imei)}</td></tr>
              <tr><th>厂商序列号</th><td>${dash(d.serial_number)}</td></tr>
              <tr><th>设备名称</th><td>${dash(d.device_name)}</td></tr>
              <tr><th>MAC</th><td>${hasBasic ? `<code>${escapeHtml(d.mac || '—')}</code>` : '<span class="text-muted">待上报</span>'}</td></tr>
            </tbody></table></div></div>
          </div>
          <div class="grid-2">
            <div class="panel" style="margin:0"><div class="panel-header"><h3>硬件信息</h3></div><div class="panel-body" style="padding:0"><table class="kv-table"><tbody>
              <tr><th>操作系统</th><td>${hasBasic
                ? `${escapeHtml(d.os || '—')}${d.os_build ? ' (Build ' + escapeHtml(d.os_build) + ')' : ''}`
                : '<span class="text-muted">待上报</span>'}</td></tr>
              <tr><th>CPU</th><td>${dash(d.cpu)}</td></tr>
              <tr><th>内存</th><td>${dash(d.memory)}</td></tr>
              <tr><th>磁盘</th><td>${dash(d.disk)}</td></tr>
              <tr><th>显卡</th><td>${dash(d.gpu)}</td></tr>
              <tr><th>BIOS</th><td>${dash(d.bios_version)}</td></tr>
            </tbody></table></div></div>
            <div class="panel" style="margin:0"><div class="panel-header"><h3>网络与连接</h3></div><div class="panel-body" style="padding:0"><table class="kv-table"><tbody>
              <tr><th>主机名</th><td>${dash(d.hostname)}</td></tr>
              <tr><th>IP 地址</th><td>${hasBasic ? `<code>${escapeHtml(d.ip || '—')}</code>` : '<span class="text-muted">待上报</span>'}</td></tr>
              <tr><th>MAC</th><td>${hasBasic ? `<code>${escapeHtml(d.mac || '—')}</code>` : '<span class="text-muted">待上报</span>'}</td></tr>
              <tr><th>子网掩码</th><td>${dash(d.subnet)}</td></tr>
              <tr><th>网关</th><td>${dash(d.gateway)}</td></tr>
              <tr><th>DNS</th><td>${dash(d.dns)}</td></tr>
              <tr><th>MQTT Client ID</th><td>${hasBasic ? `<code>${escapeHtml(d.mqtt_client_id || '—')}</code>` : '<span class="text-muted">待上报</span>'}</td></tr>
            </tbody></table></div></div>
          </div>`;
      }

      function requestDeviceReport(deviceSn) {
        U.confirm(
          '向设备发送上报通知？设备在线时将上报基本信息、已装应用列表与策略快照。',
          async () => {
            try {
              const ret = await MDMApi.notifyDeviceSnapshotReport(deviceSn);
              if (ret && ret.skipped) {
                U.toast(ret.message || '设备离线，通知未下发', 'error');
                return;
              }
              U.toast((ret && ret.message) || '已通知设备上报');
            } catch (e) {
              U.toast(e.message || '操作失败', 'error');
            }
          }
        );
      }

      function renderSnapshot(snapshot) {
        if (!snapshot) {
          snapshotPanel.innerHTML = pendingPanel('暂无快照数据');
          return;
        }
        const diffs = snapshot.diffs || [];
        const expected = snapshot.expected || [];
        const current = snapshot.current || [];

        const expMap = {};
        const curMap = {};
        expected.forEach(it => {
          const code = String(it.policy_code || '').trim();
          if (code) expMap[code] = it;
        });
        current.forEach(it => {
          const code = String(it.policy_code || '').trim();
          if (code) curMap[code] = it;
        });
        const diffMap = {};
        diffs.forEach(d => {
          const code = String(d.policy_code || '').trim();
          if (code) diffMap[code] = d;
        });

        // 同一策略一行：预期 + 当前合并（含 APP_MANAGEMENT）
        const codes = Array.from(
          new Set([...Object.keys(expMap), ...Object.keys(curMap)])
        ).sort((a, b) => a.localeCompare(b));

        const summaryHtml = codes.length
          ? (diffs.length
            ? `<span class="badge badge-err">存在 ${diffs.length} 项不合规</span>
               <span class="text-muted" style="margin-left:8px;font-size:12px">共 ${codes.length} 项策略</span>`
            : `<span class="badge badge-ok">全部合规</span>
               <span class="text-muted" style="margin-left:8px;font-size:12px">共 ${codes.length} 项策略</span>`)
          : `<span class="text-muted">暂无策略快照</span>`;

        const emptyCell = `<span class="text-muted">无</span>`;

        const rowsHtml = codes.length
          ? codes.map(code => {
            const exp = expMap[code];
            const cur = curMap[code];
            const diff = diffMap[code];
            const ok = !diff;
            const diffHint = diff
              ? (diff.field_diffs || [])
                .map(f => U.formatPolicyDiffFieldHtml(code, f))
                .filter(Boolean)
                .join('')
              : '';
            return `<tr class="${ok ? '' : 'snap-row-mismatch'}">
              <td class="snap-col-name">
                <strong>${escapeHtml(policyName(code))}</strong>
              </td>
              <td class="snap-col-side">${exp ? U.formatPolicyParamHtml(code, exp.param) : emptyCell}</td>
              <td class="snap-col-side">${cur ? U.formatPolicyParamHtml(code, cur.param) : emptyCell}</td>
              <td class="snap-col-status">
                ${ok ? U.badgeStatus('compliant') : U.badgeStatus('non-compliant')}
                ${!ok && diffHint ? `<div class="snap-diff-cell">${diffHint}</div>` : ''}
                ${!ok && (diff && diff.message) ? `<div class="text-muted" style="margin-top:4px;font-size:12px">${escapeHtml(diff.message)}</div>` : ''}
              </td>
            </tr>`;
          }).join('')
          : `<tr><td colspan="4" class="text-muted" style="text-align:center;padding:28px">暂无策略快照数据</td></tr>`;

        snapshotPanel.innerHTML = `
          <div class="panel">
            <div class="panel-header">
              <h3>策略快照对比</h3>
              <div class="extra">${summaryHtml}</div>
            </div>
            <div class="panel-body" style="padding:0;overflow:auto">
              <table class="data-table snap-compare-table">
                <thead>
                  <tr>
                    <th class="snap-col-name">策略</th>
                    <th class="snap-col-side">预期快照</th>
                    <th class="snap-col-side">当前快照</th>
                    <th class="snap-col-status">是否合规</th>
                  </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
              </table>
            </div>
          </div>`;
      }

      function renderApps(items) {
        const apps = items || [];
        appsPanel.innerHTML = `<div class="panel"><div class="panel-body" style="padding:0"><table class="data-table"><thead><tr>
          <th>应用名称</th><th>包名</th><th>版本</th>
        </tr></thead><tbody>${apps.length ? apps.map(a => `<tr>
          <td>${escapeHtml(a.app_name)}</td>
          <td><code>${escapeHtml(a.bundle_name || '—')}</code></td>
          <td>${escapeHtml(a.version_name || '—')}</td>
        </tr>`).join('') : '<tr><td colspan="3" class="text-muted">暂无已安装应用</td></tr>'}</tbody></table></div></div>`;
      }

      function bindTrackPagination() {
        trackPanel?.querySelectorAll('#track-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === trackPage) return;
            trackPage = p;
            loadTrack();
          });
        });
      }

      function renderTrack(data) {
        const items = (data && data.items) || [];
        const total = Number(data && data.total) || 0;
        trackPanel.innerHTML = `
          <div class="panel">
            <div class="panel-header">
              <h3>位置上报记录</h3>
              <span class="extra">共 ${total} 条 · 按上报时间倒序</span>
            </div>
            <div class="panel-body" style="padding:0">
              <table class="data-table"><thead><tr>
                <th>上报时间</th><th>经度</th><th>纬度</th>
              </tr></thead><tbody>${items.length ? items.map(r => `<tr>
                <td>${escapeHtml(r.report_time || '—')}</td>
                <td><code>${escapeHtml(r.longitude || '—')}</code></td>
                <td><code>${escapeHtml(r.latitude || '—')}</code></td>
              </tr>`).join('') : '<tr><td colspan="3" class="text-muted">暂无轨迹数据</td></tr>'}</tbody></table>
            </div>
            <div id="track-pagination" style="padding:12px 16px">${U.pagination(total, trackPage, trackPageSize, { unit: '条', pageItems: items.length })}</div>
          </div>`;
        bindTrackPagination();
      }

      async function loadBasic() {
        if (!basicPanel) return;
        const seq = ++loadSeq.basic;
        basicPanel.innerHTML = `<div class="panel"><div class="panel-body text-muted">正在加载基本信息…</div></div>`;
        try {
          if (!window.MDMApi || !MDMApi.getDevice) {
            throw new Error('API 客户端未加载，请强制刷新页面（Ctrl+F5）');
          }
          const device = await MDMApi.getDevice(sn);
          if (seq !== loadSeq.basic) return;
          renderHeader(device);
          renderBasic(device);
        } catch (e) {
          if (seq !== loadSeq.basic) return;
          const msg = e.message || '加载失败';
          basicPanel.innerHTML = pendingPanel(msg);
        }
      }

      async function loadSnapshot() {
        if (!snapshotPanel) return;
        const seq = ++loadSeq.snapshot;
        snapshotPanel.innerHTML = `<div class="panel"><div class="panel-body text-muted">正在加载快照…</div></div>`;
        try {
          // 预加载应用目录，便于把 App ID / 包名解析成应用名
          await U.loadAppInstallCatalog().catch(() => null);
          if (seq !== loadSeq.snapshot) return;
          const snapshot = await MDMApi.getDeviceSnapshot(sn);
          if (seq !== loadSeq.snapshot) return;
          renderSnapshot(snapshot);
        } catch (e) {
          if (seq !== loadSeq.snapshot) return;
          snapshotPanel.innerHTML = pendingPanel(e.message || '快照加载失败');
        }
      }

      async function loadApps() {
        if (!appsPanel) return;
        const seq = ++loadSeq.apps;
        appsPanel.innerHTML = `<div class="panel"><div class="panel-body text-muted">正在加载已安装应用…</div></div>`;
        try {
          const appData = await MDMApi.listDeviceApps(sn);
          if (seq !== loadSeq.apps) return;
          renderApps((appData && appData.items) || []);
        } catch (e) {
          if (seq !== loadSeq.apps) return;
          appsPanel.innerHTML = pendingPanel(e.message || '已安装应用加载失败');
        }
      }

      async function loadTrack() {
        if (!trackPanel) return;
        const seq = ++loadSeq.track;
        trackPanel.innerHTML = `<div class="panel"><div class="panel-body text-muted">正在加载轨迹…</div></div>`;
        try {
          const data = await MDMApi.listDeviceLocations(sn, {
            page: trackPage,
            page_size: trackPageSize
          });
          if (seq !== loadSeq.track) return;
          renderTrack(data);
        } catch (e) {
          if (seq !== loadSeq.track) return;
          trackPanel.innerHTML = pendingPanel(e.message || '轨迹加载失败');
        }
      }

      function overallBadge(status, label) {
        const s = String(status || '');
        const text = escapeHtml(label || s || '—');
        // 已通过=绿；审批中=琥珀；已驳回=红（与审批中区分）
        if (s === 'APPROVED') return `<span class="badge badge-ok">${text}</span>`;
        if (s === 'REJECTED') return `<span class="badge badge-err">${text}</span>`;
        if (s === 'PENDING') return `<span class="badge badge-bad">${text}</span>`;
        return `<span class="badge badge-free">${text}</span>`;
      }

      function stepStatusBadge(status, label, isCurrent) {
        const s = String(status || '');
        const text = escapeHtml(label || s || '—');
        const cur = isCurrent ? ' ← 当前' : '';
        if (s === 'APPROVED') return `<span class="badge badge-ok">${text}</span>`;
        if (s === 'REJECTED') return `<span class="badge badge-err">${text}</span>`;
        if (s === 'PENDING') return `<span class="badge badge-bad">${text}${cur}</span>`;
        return `<span class="badge badge-off">${text}</span>`;
      }

      function bindBizcardPanelEvents() {
        if (!bizcardPanel) return;
        bizcardPanel.querySelectorAll('[data-biz-kind]').forEach(btn => {
          btn.addEventListener('click', () => {
            const next = btn.getAttribute('data-biz-kind') || 'mine';
            if (next === bizKind) return;
            bizKind = next;
            bizPage = 1;
            loadBizCards();
          });
        });
        bizcardPanel.querySelectorAll('[data-biz-id]').forEach(btn => {
          btn.addEventListener('click', () => {
            openBizCardDetail(btn.getAttribute('data-biz-id') || '');
          });
        });
        bizcardPanel.querySelectorAll('#biz-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === bizPage) return;
            bizPage = p;
            loadBizCards();
          });
        });
      }

      function renderBizCards(data) {
        if (!bizcardPanel) return;
        if (!data || data.bound === false) {
          bizcardPanel.innerHTML = pendingPanel(
            (data && data.message) || '设备未绑定成员，无业务卡片'
          );
          return;
        }
        const items = (data && data.items) || [];
        const total = Number((data && data.total) || 0);
        const kind = (data && data.kind) || bizKind;
        const showApplicant = kind === 'todo';
        const colCount = showApplicant ? 7 : 6;

        const rows = items.length
          ? items.map(it => {
              const applicant = it.applicantName
                ? `${escapeHtml(it.applicantName)}${it.applicantId ? '（' + escapeHtml(it.applicantId) + '）' : ''}`
                : escapeHtml(it.applicantId || '—');
              const progress = it.totalStep
                ? `${escapeHtml(String(it.currentStep || '—'))}/${escapeHtml(String(it.totalStep))}`
                : '—';
              return `<tr>
                <td>${escapeHtml(it.title || '—')}</td>
                <td style="max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${escapeHtml(it.content || '')}">${escapeHtml(it.content || '—')}</td>
                ${showApplicant ? `<td>${applicant}</td>` : ''}
                <td>${escapeHtml(it.submitTime || '—')}</td>
                <td>${overallBadge(it.overallStatus, it.overallStatusLabel)}</td>
                <td>${progress}</td>
                <td><button type="button" class="btn btn-sm" data-biz-id="${escapeHtml(it.bizId)}">详情</button></td>
              </tr>`;
            }).join('')
          : `<tr><td colspan="${colCount}" class="text-muted" style="text-align:center;padding:24px">${
              kind === 'todo' ? '暂无待我审核的单据' : '暂无我的提交记录'
            }</td></tr>`;

        bizcardPanel.innerHTML = `
          <div class="panel">
            <div class="panel-header" style="display:flex;flex-wrap:wrap;align-items:center;gap:10px">
              <div role="group" aria-label="业务卡片类型" style="display:flex;gap:8px">
                <button type="button" class="btn btn-sm${kind === 'mine' ? ' btn-primary' : ''}" data-biz-kind="mine">我的提交</button>
                <button type="button" class="btn btn-sm${kind === 'todo' ? ' btn-primary' : ''}" data-biz-kind="todo">待我审核</button>
              </div>
            </div>
            <div class="panel-body" style="padding:0">
              <table class="data-table">
                <thead><tr>
                  <th>标题</th><th>内容</th>${showApplicant ? '<th>提交人</th>' : ''}<th>提交时间</th><th>状态</th><th>进度</th><th>操作</th>
                </tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
            <div id="biz-pagination" style="padding:12px 16px">${U.pagination(total, bizPage, bizPageSize, { unit: '条', pageItems: items.length })}</div>
          </div>`;
        bindBizcardPanelEvents();
      }

      async function loadBizCards() {
        if (!bizcardPanel) return;
        const seq = ++loadSeq.bizcard;
        bizcardPanel.innerHTML = `<div class="panel"><div class="panel-body text-muted">正在加载业务卡片…</div></div>`;
        try {
          const data = await MDMApi.listDeviceBizCards(sn, {
            kind: bizKind,
            page: bizPage,
            page_size: bizPageSize
          });
          if (seq !== loadSeq.bizcard) return;
          renderBizCards(data);
        } catch (e) {
          if (seq !== loadSeq.bizcard) return;
          bizcardPanel.innerHTML = pendingPanel(e.message || '业务卡片加载失败');
        }
      }

      async function openBizCardDetail(bizId) {
        if (!bizId) return;
        try {
          const detail = await MDMApi.getDeviceBizCard(sn, bizId);
          const applicant = detail.applicantName
            ? `${escapeHtml(detail.applicantName)}${detail.applicantId ? '（' + escapeHtml(detail.applicantId) + '）' : ''}`
            : escapeHtml(detail.applicantId || '—');
          const overallRejected = String(detail.overallStatus || '') === 'REJECTED';
          const steps = (detail.steps || []).map(s => {
            const who = s.handlerName
              ? `${escapeHtml(s.handlerName)}${s.handlerId ? '（' + escapeHtml(s.handlerId) + '）' : ''}`
              : escapeHtml(s.handlerId || '—');
            // 整单已驳回：后续未轮到的 WAITING 不再显示「等待中」，改为「未进行」
            const skippedAfterReject =
              overallRejected && String(s.status || '') === 'WAITING';
            const statusHtml = skippedAfterReject
              ? '<span class="text-muted">未进行</span>'
              : stepStatusBadge(s.status, s.statusLabel, String(s.status || '') === 'PENDING');
            // 仅展示实际操作/审核完成时间；待审、未进行不展示 occurTime（待办到达时间）
            const opTime = skippedAfterReject ? null : s.finishTime;
            const reasonText =
              String(s.status || '') === 'REJECTED' && s.rejectReason
                ? escapeHtml(s.rejectReason)
                : '—';
            return `<tr>
              <td>${who}</td>
              <td>${statusHtml}</td>
              <td>${escapeHtml(opTime || '—')}</td>
              <td style="max-width:240px;white-space:pre-wrap;line-height:1.5">${reasonText}</td>
            </tr>`;
          }).join('') || '<tr><td colspan="4" class="text-muted">暂无步骤</td></tr>';

          // 整单状态合并进度：审批中带 当前/总数；终态只显示结果
          const statusLabel = detail.overallStatusLabel || detail.overallStatus || '—';
          const cur = detail.currentStep;
          const total = detail.totalStep;
          let statusText = escapeHtml(statusLabel);
          if (String(detail.overallStatus || '') === 'PENDING' && cur != null && total != null) {
            statusText = `${escapeHtml(statusLabel)}（${escapeHtml(String(cur))}/${escapeHtml(String(total))}）`;
          }

          U.modal({
            title: '业务卡片详情',
            size: 'lg',
            okText: '关闭',
            body: `
              <div style="margin-bottom:14px">
                <table class="kv-table"><tbody>
                  <tr><th>标题</th><td>${escapeHtml(detail.title || '—')}</td></tr>
                  <tr><th>内容</th><td style="white-space:pre-wrap;line-height:1.6">${escapeHtml(detail.content || '—')}</td></tr>
                  <tr><th>提交人</th><td>${applicant}</td></tr>
                  <tr><th>提交时间</th><td>${escapeHtml(detail.submitTime || '—')}</td></tr>
                  <tr><th>整单状态</th><td>${statusText}</td></tr>
                  <tr><th>当前处理人</th><td>${
                    detail.currentHandlerId
                      ? escapeHtml((detail.currentHandlerName || '') + (detail.currentHandlerName ? '（' + detail.currentHandlerId + '）' : detail.currentHandlerId))
                      : '—'
                  }</td></tr>
                </tbody></table>
              </div>
              <h4 style="margin:0 0 8px;font-size:14px">审批流程</h4>
              <table class="data-table"><thead><tr>
                <th>审批人</th><th>状态</th><th>操作时间</th><th>驳回原因</th>
              </tr></thead><tbody>${steps}</tbody></table>`
          });
        } catch (e) {
          U.toast(e.message || '详情加载失败', 'error');
        }
      }

      function loadTab(name) {
        const tab = (name || 'basic').trim();
        if (tab === 'basic') return loadBasic();
        if (tab === 'snapshot') return loadSnapshot();
        if (tab === 'apps') return loadApps();
        if (tab === 'bizcard') return loadBizCards();
        if (tab === 'track') return loadTrack();
      }

      const tabs = tabsWrap ? tabsWrap.querySelectorAll('.tab-item') : [];
      const panels = tabsWrap ? tabsWrap.querySelectorAll('.tab-panel') : [];
      tabs.forEach(tab => {
        tab.addEventListener('click', () => {
          tabs.forEach(t => t.classList.remove('active'));
          panels.forEach(p => p.classList.remove('active'));
          tab.classList.add('active');
          const panel = tabsWrap.querySelector(`[data-panel="${tab.dataset.tab}"]`);
          if (panel) panel.classList.add('active');
          if (tab.dataset.tab === 'track') trackPage = 1;
          if (tab.dataset.tab === 'bizcard') {
            bizPage = 1;
          }
          loadTab(tab.dataset.tab);
        });
      });

      await loadTab('basic');
    }
  });
})();
