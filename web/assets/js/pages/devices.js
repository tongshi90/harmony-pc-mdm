(async function () {
  const U = MDMUtils;
  const SN_MAX_LEN = 64;
  const BATCH_MAX = 500;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  let list = [];
  let total = 0;
  let page = 1;
  const pageSize = 20;
  let keyword = '';
  /** chip: '' | online | offline | noncompliant | unbound */
  let chip = '';
  let loadError = '';
  let stats = { total: 0, online: 0, offline: 0, noncompliant: 0 };

  function chipToParams() {
    if (chip === 'online') return { status: 'online', bind: 'bound', compliance: '' };
    if (chip === 'offline') return { status: 'offline', bind: 'bound', compliance: '' };
    if (chip === 'unbound') return { status: '', bind: 'unbound', compliance: '' };
    if (chip === 'noncompliant') return { status: '', bind: '', compliance: 'noncompliant' };
    return { status: '', bind: '', compliance: '' };
  }

  async function loadStats() {
    try {
      const [all, online, offline, unbound, noncompliant] = await Promise.all([
        MDMApi.listDevices({ page: 1, page_size: 1 }),
        MDMApi.listDevices({ status: 'online', bind: 'bound', page: 1, page_size: 1 }),
        MDMApi.listDevices({ status: 'offline', bind: 'bound', page: 1, page_size: 1 }),
        MDMApi.listDevices({ bind: 'unbound', page: 1, page_size: 1 }),
        MDMApi.listDevices({ compliance: 'noncompliant', page: 1, page_size: 1 })
      ]);
      stats = {
        total: (all && all.total) || 0,
        online: (online && online.total) || 0,
        offline: (offline && offline.total) || 0,
        noncompliant: (noncompliant && noncompliant.total) || 0,
        unbound: (unbound && unbound.total) || 0
      };
    } catch (_) {
      /* keep previous */
    }
  }

  async function loadDevices() {
    try {
      const params = chipToParams();
      const data = await MDMApi.listDevices({
        keyword,
        status: params.status,
        bind: params.bind,
        compliance: params.compliance,
        page,
        page_size: pageSize
      });
      list = (data && data.items) || [];
      total = data.total || 0;
      page = data.page || page;
      loadError = '';
    } catch (e) {
      list = [];
      total = 0;
      loadError = e.message || '加载失败';
    }
  }

  function summaryHtml() {
    return `
      <section class="summary summary-5" aria-label="关键指标" id="device-summary">
        <div class="sum-card s1"><div class="k">在册终端</div><div class="v">${U.fmt(stats.total)}</div></div>
        <div class="sum-card s2"><div class="k">在线</div><div class="v">${U.fmt(stats.online)}</div></div>
        <div class="sum-card s3"><div class="k">离线</div><div class="v">${U.fmt(stats.offline)}</div></div>
        <div class="sum-card s4"><div class="k">不合规</div><div class="v">${U.fmt(stats.noncompliant || 0)}</div></div>
        <div class="sum-card s5"><div class="k">未绑定</div><div class="v">${U.fmt(stats.unbound || 0)}</div></div>
      </section>`;
  }

  function statusBadge(d) {
    if (!d.bound) return '<span class="badge badge-free">未绑定</span>';
    if (d.status === 'online') return '<span class="badge badge-ok">在线</span>';
    return '<span class="badge badge-off">离线</span>';
  }

  function complianceBadge(d) {
    if (!d.bound) return '<span class="badge badge-free">—</span>';
    const bad = d.compliance === 'non-compliant' || d.compliance === 'noncompliant';
    return bad
      ? '<span class="badge badge-bad">不合规</span>'
      : '<span class="badge badge-ok">合规</span>';
  }

  function diffLabel(d) {
    const n = Number(d.diff_count);
    if (!d.bound) return '—';
    if (!Number.isFinite(n) || n <= 0) return '—';
    return `${n} 项差异`;
  }

  function tableHtml() {
    if (loadError) {
      return `<div class="panel"><div class="panel-body text-muted">${escapeHtml(loadError)}</div></div>`;
    }
    const rows = list.length ? list.map(d => {
      const bound = !!d.bound;
      const online = d.status === 'online';
      const bad = bound && (d.compliance === 'non-compliant' || d.compliance === 'noncompliant');
      const dept = bound ? (d.department_path || d.department_name || '—') : '—';
      const name = bound ? escapeHtml(d.member_name || '—') : '未绑定';
      const lamp = bound && online ? 'lamp on' : 'lamp';
      let actions = '';
      if (!bound) {
        actions = `<div class="row-act">
          <button type="button" class="link-btn btn-del-device" data-sn="${escapeHtml(d.sn)}">删除</button>
        </div>`;
      } else {
        const retryBtn = bad && online
          ? `<button type="button" class="link-btn solid btn-retry-policy" data-sn="${escapeHtml(d.sn)}">重试</button>`
          : '';
        actions = `<div class="row-act">
          ${retryBtn}
          <button class="link-btn solid btn-dispatch-policy" type="button"
            data-member-id="${escapeHtml(d.member_id || '')}"
            data-member-name="${escapeHtml(d.member_name || '')}">下发</button>
          <a class="link-btn" href="${U.href('deviceDetail', { sn: d.sn })}">详情</a>
        </div>`;
      }
      return `<tr class="${bad ? 'is-selected' : ''}">
        <td>
          <div class="who">
            <span class="${lamp}"></span>
            <span class="name"${bound ? '' : ' style="color:var(--mute)"'}>${name}</span>
          </div>
        </td>
        <td class="dept" style="color:var(--mute)">${escapeHtml(dept)}</td>
        <td><span class="sn">${escapeHtml(d.sn)}</span></td>
        <td>${statusBadge(d)}</td>
        <td>${complianceBadge(d)}</td>
        <td style="color:${bad ? 'var(--error)' : 'var(--mute)'}">${escapeHtml(diffLabel(d))}</td>
        <td style="color:var(--mute)">${escapeHtml(d.online_time || (bound ? '—' : '尚未上线'))}</td>
        <td style="min-width:160px">${actions}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" class="text-muted" style="text-align:center;padding:28px">暂无设备</td></tr>';

    return `
      <section class="panel">
        <div class="toolbar">
          <label class="search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
            <input type="search" id="device-search" placeholder="序列号、姓名" value="${escapeHtml(keyword)}">
          </label>
          <div class="chips" id="device-chips">
            <button class="chip${chip === '' ? ' is-on' : ''}" type="button" data-chip="">全部</button>
            <button class="chip${chip === 'online' ? ' is-on' : ''}" type="button" data-chip="online">在线</button>
            <button class="chip${chip === 'offline' ? ' is-on' : ''}" type="button" data-chip="offline">离线</button>
            <button class="chip${chip === 'unbound' ? ' is-on' : ''}" type="button" data-chip="unbound">未绑定</button>
            <button class="chip${chip === 'noncompliant' ? ' is-on' : ''}" type="button" data-chip="noncompliant">不合规</button>
          </div>
          <div class="spacer"></div>
          <span class="count">显示 ${list.length} / 共 ${U.fmt(total)} 台</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th style="width:12%">使用人</th>
              <th style="width:18%">部门</th>
              <th style="width:18%">序列号</th>
              <th style="width:9%">状态</th>
              <th style="width:9%">合规</th>
              <th style="width:10%">差异</th>
              <th style="width:12%">最后在线</th>
              <th style="width:12%;text-align:right">操作</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="panel-foot">
          <span>第 ${page} 页 · 每页 ${pageSize} 台</span>
          <div id="device-pagination">${U.pagination(total, page, pageSize, { unit: '台', pageItems: list.length })}</div>
        </div>
      </section>`;
  }

  /** 解析多行 / 逗号 / 分号分隔的 SN 文本 */
  function parseSnText(raw) {
    const parts = String(raw || '')
      .split(/[\n\r,;，；\t]+/)
      .map(s => s.trim())
      .filter(Boolean);
    const seen = new Set();
    const sns = [];
    const localDupes = [];
    const invalid = [];
    for (const sn of parts) {
      if (sn.length > SN_MAX_LEN) {
        invalid.push({ sn, reason: `长度超过 ${SN_MAX_LEN}` });
        continue;
      }
      if (seen.has(sn)) {
        localDupes.push(sn);
        continue;
      }
      seen.add(sn);
      sns.push(sn);
    }
    return { sns, localDupes, invalid };
  }

  function openRegisterModal(onSuccess) {
    U.modal({
      title: '登记设备',
      okText: '提交登记',
      body: `
        <p class="text-muted" style="margin:0 0 12px;font-size:13px;line-height:1.5">
          每行一个 SN，也支持逗号或分号分隔。提交前会本地去重；已存在的 SN 会在结果中标出失败原因。
        </p>
        <label class="form-field" style="display:block;margin-bottom:12px">
          <span style="display:block;margin-bottom:6px;font-size:13px">序列号列表</span>
          <textarea id="device-sn-input" rows="8" placeholder="例如：&#10;SN001&#10;SN002,SN003"
            style="width:100%;box-sizing:border-box;resize:vertical;font-family:ui-monospace,monospace;font-size:13px"></textarea>
        </label>
        <div id="device-sn-preview" class="text-muted" style="font-size:12px;min-height:1.4em"></div>
        <div id="device-sn-result" style="margin-top:12px;display:none"></div>`,
      onOk: async () => {
        const ta = document.getElementById('device-sn-input');
        const resultEl = document.getElementById('device-sn-result');
        const { sns, invalid } = parseSnText(ta ? ta.value : '');
        if (!sns.length) {
          U.toast(invalid.length ? '没有有效的 SN' : '请至少填写一个 SN', 'error');
          return false;
        }
        if (sns.length > BATCH_MAX) {
          U.toast(`一次最多登记 ${BATCH_MAX} 个 SN`, 'error');
          return false;
        }
        try {
          const data = await MDMApi.batchCreateDevices(sns);
          const created = (data && data.created) || [];
          const failed = (data && data.failed) || [];
          const failRows = [
            ...invalid.map(x => ({ sn: x.sn, reason: x.reason })),
            ...failed
          ];
          if (resultEl) {
            resultEl.style.display = 'block';
            resultEl.innerHTML = `
              <div style="font-size:13px;margin-bottom:8px">
                成功 <strong style="color:var(--ok,#0a7)">${created.length}</strong> 台
                ${failRows.length ? `，失败 <strong style="color:var(--error)">${failRows.length}</strong> 条` : ''}
              </div>
              ${failRows.length
                ? `<div style="max-height:160px;overflow:auto;border:1px solid var(--border);border-radius:6px">
                    <table class="data-table" style="margin:0"><thead><tr><th>SN</th><th>原因</th></tr></thead>
                    <tbody>${failRows.map(f => `<tr><td><code>${escapeHtml(f.sn)}</code></td><td>${escapeHtml(f.reason || '')}</td></tr>`).join('')}</tbody>
                    </table></div>`
                : ''}`;
          }
          if (created.length) {
            U.toast(`已登记 ${created.length} 台设备`);
            if (typeof onSuccess === 'function') onSuccess();
          } else {
            U.toast('没有新登记成功的设备', 'error');
          }
          // 有失败或半成功时保留弹窗便于查看明细
          if (failRows.length) return false;
          return true;
        } catch (e) {
          U.toast(e.message || '登记失败', 'error');
          return false;
        }
      }
    });

    const ta = document.getElementById('device-sn-input');
    const preview = document.getElementById('device-sn-preview');

    function refreshPreview() {
      if (!preview || !ta) return;
      const { sns, localDupes, invalid } = parseSnText(ta.value);
      const bits = [`有效 ${sns.length} 个`];
      if (localDupes.length) bits.push(`本地重复已忽略 ${localDupes.length}`);
      if (invalid.length) bits.push(`格式无效 ${invalid.length}`);
      if (sns.length > BATCH_MAX) bits.push(`超出上限 ${BATCH_MAX}`);
      preview.textContent = bits.join(' · ');
    }

    if (ta) {
      ta.addEventListener('input', refreshPreview);
      setTimeout(() => ta.focus(), 0);
    }
    refreshPreview();
  }

  await Promise.all([loadStats(), loadDevices()]);

  MDMLayout.mount({
    pageId: 'devices',
    title: '设备管理',
    actions: `<button type="button" class="btn btn-primary" id="btn-register-device">登记设备</button>`,
    content: `
      <div id="device-summary-wrap">${summaryHtml()}</div>
      <div id="device-list">${tableHtml()}</div>`,
    onMount() {
      const listEl = document.getElementById('device-list');
      const summaryEl = document.getElementById('device-summary-wrap');

      async function refresh(opts) {
        if (opts && opts.reloadStats) await loadStats();
        await loadDevices();
        if (summaryEl) summaryEl.innerHTML = summaryHtml();
        if (listEl) listEl.innerHTML = tableHtml();
        bindList();
      }

      document.getElementById('btn-register-device')?.addEventListener('click', () => {
        openRegisterModal(() => refresh({ reloadStats: true }));
      });

      function bindList() {
        document.querySelectorAll('#device-chips .chip').forEach(btn => {
          btn.addEventListener('click', () => {
            const next = btn.dataset.chip || '';
            if (next === chip) return;
            chip = next;
            page = 1;
            refresh();
          });
        });

        const searchInput = document.getElementById('device-search');
        let searchTimer = null;
        if (searchInput) {
          searchInput.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
              keyword = searchInput.value.trim();
              page = 1;
              refresh();
            }, 300);
          });
        }

        document.querySelectorAll('.btn-retry-policy').forEach(btn => {
          btn.addEventListener('click', () => {
            const sn = (btn.dataset.sn || '').trim();
            if (!sn) return;
            U.confirm('向设备补发策略拉取通知？设备在线时将重新拉取云侧预期策略。', async () => {
              try {
                const ret = await MDMApi.notifyDeviceStrategyPull(sn);
                if (ret && ret.skipped) {
                  U.toast(ret.message || '未下发', 'error');
                  return;
                }
                U.toast((ret && ret.message) || '已通知设备重新拉取策略');
              } catch (e) {
                U.toast(e.message || '补发失败', 'error');
              }
            });
          });
        });

        document.querySelectorAll('.btn-dispatch-policy').forEach(btn => {
          btn.addEventListener('click', () => {
            if (!btn.dataset.memberId) {
              U.toast('设备未绑定使用人，无法下发策略', 'error');
              return;
            }
            const memberName = (btn.dataset.memberName || '').trim() || '未知用户';
            location.href = U.href('sceneDispatchCreate', {
              targetType: 'member',
              memberId: btn.dataset.memberId,
              memberName,
              taskName: `${memberName}的设备策略下发`
            });
          });
        });

        document.querySelectorAll('.btn-del-device').forEach(btn => {
          btn.addEventListener('click', () => {
            const sn = (btn.dataset.sn || '').trim();
            if (!sn) return;
            U.confirm('确认删除该未绑定设备？删除后不可恢复。', async () => {
              try {
                await MDMApi.deleteDevice(sn);
                U.toast('已删除');
                refresh({ reloadStats: true });
              } catch (e) {
                U.toast(e.message || '删除失败', 'error');
              }
            });
          });
        });

        document.querySelectorAll('#device-pagination .page-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const p = Number(btn.dataset.page);
            if (!p || p === page) return;
            page = p;
            refresh();
          });
        });
      }

      bindList();
    }
  });
})();
