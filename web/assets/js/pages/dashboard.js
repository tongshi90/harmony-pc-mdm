(async function () {
  const U = MDMUtils;

  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function fmt(n) {
    return typeof U.fmt === 'function' ? U.fmt(n) : String(n == null ? 0 : n);
  }

  let orgTree = [];
  let orgPath = [];
  let appsData = [];

  const PIE_COLORS = [
    '#0f766e', '#14b8a6', '#2dd4bf', '#5eead4', '#99f6e4',
    '#64748b', '#94a3b8', '#cbd5e1', '#f59e0b', '#f97316'
  ];

  function icoPerson() {
    return `<span class="dash-org-ico" aria-hidden="true"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 1.5c-2.67 0-8 1.34-8 4V15h16v-1.5c0-2.66-5.33-4-8-4Z"/></svg></span>`;
  }

  function icoDevice() {
    return `<span class="dash-org-ico" aria-hidden="true"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v6A1.5 1.5 0 0 1 12.5 11H9l1 2h2v1H4v-1h2l1-2H3.5A1.5 1.5 0 0 1 2 9.5v-6Zm1.5-.5a.5.5 0 0 0-.5.5v6a.5.5 0 0 0 .5.5h9a.5.5 0 0 0 .5-.5v-6a.5.5 0 0 0-.5-.5h-9Z"/></svg></span>`;
  }

  function devicePanelHtml(devices) {
    const d = devices || {};
    const total = Number(d.total) || 0;
    const online = Number(d.online) || 0;
    const offline = Number(d.offline) || 0;
    const unbound = Number(d.unbound) || 0;
    const noncompliant = Number(d.noncompliant) || 0;
    const bound = online + offline;
    const href = (q) => (q ? U.href('devices', q) : U.href('devices'));
    const parts = [
      { key: 'online', label: '在线设备数', value: online, q: { status: '1', bind: '1' } },
      { key: 'offline', label: '离线设备数', value: offline, q: { status: '2', bind: '1' } },
      { key: 'unbound', label: '未绑定设备数', value: unbound, q: { bind: '0' } }
    ];
    const segs = parts
      .filter(p => p.value > 0)
      .map(p => `<span class="dash-dev-seg is-${p.key}" style="flex:${p.value}"></span>`)
      .join('');
    const col = p => `<a class="dash-dev-col is-${p.key}" href="${href(p.q)}">
        <span class="k"><i class="dash-dev-dot is-${p.key}" aria-hidden="true"></i>${p.label}</span>
        <span class="v">${fmt(p.value)}</span>
      </a>`;
    return `
      <section class="panel dash-panel" id="dash-dev-panel" aria-label="设备统计">
        <div class="panel-header">
          <h3>在册终端</h3>
          <a class="dash-dev-total" href="${href()}">${fmt(total)}</a>
        </div>
        <div class="panel-body dash-dev-body">
          <div class="dash-dev-track" aria-hidden="true">${segs || '<span class="dash-dev-seg is-offline" style="flex:1"></span>'}</div>
          <div class="dash-dev-grid">
            ${parts.map(col).join('')}
            <a class="dash-dev-nc${noncompliant > 0 ? ' is-alert' : ''}" href="${href({})}">已绑定设备数 ${fmt(bound)} · 不合规设备数 ${fmt(noncompliant)}</a>
          </div>
        </div>
      </section>`;
  }

  function orgUnbound(row) {
    if (row && row.unbound_member_count != null) return Math.max(0, Number(row.unbound_member_count) || 0);
    const members = Number(row && row.member_count) || 0;
    const devices = Number(row && row.device_count) || 0;
    return Math.max(0, members - devices);
  }

  function orgTipText(row, extra) {
    const members = Number(row.member_count) || 0;
    const devices = Number(row.device_count) || 0;
    const unbound = orgUnbound(row);
    let text = `${row.name || '—'}｜成员 ${fmt(members)}｜已绑终端 ${fmt(devices)}｜未绑成员 ${fmt(unbound)}`;
    if (extra) text += `｜${extra}`;
    return text;
  }

  function orgBarPct(v, max) {
    const m = Math.max(Number(max) || 0, 0);
    const n = Math.max(Number(v) || 0, 0);
    if (m <= 0 || n <= 0) return 0;
    return Math.max(2, Math.round((n / m) * 1000) / 10);
  }

  function findOrgNode(nodes, id) {
    const target = String(id);
    for (const n of nodes || []) {
      if (String(n.id) === target) return n;
      const hit = findOrgNode(n.children || [], target);
      if (hit) return hit;
    }
    return null;
  }

  function currentOrgParent() {
    if (!orgPath.length) return null;
    return findOrgNode(orgTree, orgPath[orgPath.length - 1]);
  }

  function currentOrgNodes() {
    if (!orgPath.length) return orgTree.slice();
    const parent = currentOrgParent();
    return (parent && parent.children) ? parent.children.slice() : [];
  }

  function orgStackRowHtml(row, maxMembers) {
    const members = Number(row.member_count) || 0;
    const devices = Number(row.device_count) || 0;
    const unbound = orgUnbound(row);
    const canDrill = !!(row.has_children || (row.children && row.children.length));
    const childCount = (row.children && row.children.length) || 0;
    const totalW = orgBarPct(members, maxMembers);
    const boundShare = members > 0 ? (devices / members) * 100 : 0;
    const freeShare = members > 0 ? (unbound / members) * 100 : 0;
    const tag = canDrill ? `${childCount} 个子分组 · 点击查看` : '末级';
    return `<button type="button"
      class="dash-org-row${canDrill ? ' is-drill' : ''}"
      data-org-id="${esc(row.id)}"
      data-org-action="${canDrill ? 'drill' : ''}"
      title="${esc(orgTipText(row, canDrill ? '点击查看下级' : ''))}"
      ${canDrill ? '' : 'disabled'}>
      <div class="dash-org-name">
        <span class="dash-org-name-text">${esc(row.name)}</span>
        <small>${tag}</small>
      </div>
      <div class="dash-org-track" style="--w:${totalW}%" aria-hidden="true">
        <span class="dash-org-seg bound" style="width:${boundShare}%"></span>
        <span class="dash-org-seg free" style="width:${freeShare}%"></span>
      </div>
      <div class="dash-org-meta">
        ${icoPerson()}<b>${fmt(members)}</b>
        <span class="dash-org-meta-sep">|</span>
        ${icoDevice()}<b>${fmt(devices)}</b>
      </div>
    </button>`;
  }

  function orgStackListHtml(items) {
    const list = (items || [])
      .slice()
      .sort((a, b) =>
        (Number(b.member_count) || 0) - (Number(a.member_count) || 0) ||
        (Number(b.device_count) || 0) - (Number(a.device_count) || 0)
      );
    if (!list.length) {
      return `<div class="dash-org-empty">该分组下暂无子分组</div>`;
    }
    const maxMembers = Math.max(...list.map(x => Number(x.member_count) || 0), 1);
    return `<div class="dash-org-list" id="dash-org-list">
      ${list.map(row => orgStackRowHtml(row, maxMembers)).join('')}
    </div>`;
  }

  function orgBreadcrumbHtml() {
    if (!orgPath.length) {
      return `<span class="extra">点击行可查看下级分组</span>`;
    }
    const parts = [`<button type="button" class="dash-org-crumb" data-org-depth="0">全部</button>`];
    orgPath.forEach((id, idx) => {
      const node = findOrgNode(orgTree, id);
      const name = (node && node.name) || id;
      const last = idx === orgPath.length - 1;
      parts.push('<span class="dash-org-sep">/</span>');
      parts.push(
        `<button type="button" class="dash-org-crumb${last ? ' is-current' : ''}" data-org-depth="${idx + 1}"${last ? ' disabled' : ''}>${esc(name)}</button>`
      );
    });
    return `<div class="dash-org-crumbs">${parts.join('')}</div>`;
  }

  function orgChartShellHtml() {
    if (!orgTree.length) {
      return `
        <section class="panel dash-panel" id="dash-org-panel">
          <div class="panel-header"><h3>组织分布</h3></div>
          <div class="panel-body text-muted" style="padding:32px;text-align:center">暂无分组数据</div>
        </section>`;
    }
    const items = currentOrgNodes();
    const backBtn = orgPath.length
      ? `<button type="button" class="btn btn-sm" id="dash-org-back">返回上一级</button>`
      : '';
    return `
      <section class="panel dash-panel" id="dash-org-panel">
        <div class="panel-header">
          <h3>组织分布</h3>
          ${orgBreadcrumbHtml()}
        </div>
        <div class="panel-body">
          <div class="dash-org-legend">
            <span><i class="dash-swatch bound"></i>${icoDevice()}已绑终端</span>
            <span><i class="dash-swatch unbound"></i>${icoPerson()}未绑成员</span>
            ${backBtn}
          </div>
          ${orgStackListHtml(items)}
        </div>
      </section>`;
  }

  function refreshOrgChart() {
    const panel = document.getElementById('dash-org-panel');
    if (!panel) return;
    const wrap = document.createElement('div');
    wrap.innerHTML = orgChartShellHtml();
    const next = wrap.firstElementChild;
    panel.replaceWith(next);
    bindOrgChart(next);
  }

  function bindOrgChart(rootEl) {
    const panel = rootEl || document.getElementById('dash-org-panel');
    if (!panel) return;

    panel.querySelectorAll('.dash-org-row.is-drill').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-org-id');
        const node = findOrgNode(orgTree, id);
        if (!node || !(node.children && node.children.length)) return;
        orgPath.push(String(id));
        refreshOrgChart();
      });
    });

    panel.querySelector('#dash-org-back')?.addEventListener('click', () => {
      if (!orgPath.length) return;
      orgPath.pop();
      refreshOrgChart();
    });

    panel.querySelectorAll('.dash-org-crumb').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.disabled) return;
        const depth = Number(btn.getAttribute('data-org-depth') || 0);
        orgPath = orgPath.slice(0, Math.max(0, depth));
        refreshOrgChart();
      });
    });
  }

  function appCoverageRate(app) {
    const total = Number(app.device_total) || 0;
    const installed = Number(app.install_count) || 0;
    if (total <= 0) return 0;
    return Math.min(100, Math.round((installed / total) * 1000) / 10);
  }

  function appPieSlices(app) {
    const versions = Array.isArray(app.versions) ? app.versions : [];
    const slices = versions
      .map((v, i) => ({
        label: v.version_name || v.version_code || `版本${i + 1}`,
        count: Number(v.install_count) || 0,
        color: PIE_COLORS[i % PIE_COLORS.length]
      }))
      .filter(s => s.count > 0);
    const installed = Number(app.install_count) || 0;
    const summed = slices.reduce((s, x) => s + x.count, 0);
    if (installed > summed) {
      slices.push({
        label: '其它已装',
        count: installed - summed,
        color: PIE_COLORS[slices.length % PIE_COLORS.length]
      });
    }
    const notInstalled = Number(app.not_installed_count) || 0;
    if (notInstalled > 0) {
      slices.push({ label: '未安装', count: notInstalled, color: '#cbd5e1' });
    }
    const total = slices.reduce((s, x) => s + x.count, 0) || 1;
    return slices.map(s => ({
      ...s,
      pct: Math.round((s.count / total) * 1000) / 10
    }));
  }

  function appPieGradient(slices) {
    let acc = 0;
    return slices.map(s => {
      const start = Math.round(acc * 10) / 10;
      acc += s.pct;
      const end = Math.min(100, Math.round(acc * 10) / 10);
      return `${s.color} ${start}% ${end}%`;
    }).join(', ');
  }

  function closeAppPieModal() {
    document.getElementById('dash-app-pie-mask')?.remove();
  }

  function openAppPieModal(app) {
    closeAppPieModal();
    const slices = appPieSlices(app);
    const stops = appPieGradient(slices);
    const rate = appCoverageRate(app);
    const legend = slices.map(s => `
      <li>
        <i style="background:${s.color}"></i>
        <span class="dash-app-pie-lb">${esc(s.label)}</span>
        <span class="dash-app-pie-n">${fmt(s.count)}</span>
        <span class="dash-app-pie-p">${s.pct}%</span>
      </li>`).join('');

    const mask = document.createElement('div');
    mask.id = 'dash-app-pie-mask';
    mask.className = 'modal-mask show';
    mask.innerHTML = `
      <div class="modal dash-app-pie-modal" role="dialog" aria-modal="true" aria-labelledby="dash-app-pie-title">
        <div class="modal-header">
          <div>
            <div id="dash-app-pie-title">${esc(app.app_name || '应用')}</div>
            <div class="dash-app-pie-sub">已装 ${fmt(app.install_count)} · 未装 ${fmt(app.not_installed_count)} · 覆盖率 ${rate}% · 设备 ${fmt(app.device_total)}</div>
          </div>
          <button type="button" class="btn btn-sm" id="dash-app-pie-close">关闭</button>
        </div>
        <div class="modal-body dash-app-pie-body">
          <div class="dash-app-pie-wrap">
            <div class="dash-app-pie" style="--pie-stops:${stops}"></div>
            <div class="dash-app-pie-hole">
              <b>${rate}%</b>
              <em>覆盖率</em>
            </div>
          </div>
          <ul class="dash-app-pie-legend">${legend || '<li class="text-muted">暂无版本数据</li>'}</ul>
        </div>
      </div>`;
    document.body.appendChild(mask);

    const onKey = e => {
      if (e.key === 'Escape') {
        closeAppPieModal();
        document.removeEventListener('keydown', onKey);
      }
    };
    document.addEventListener('keydown', onKey);
    mask.addEventListener('click', e => {
      if (e.target === mask) closeAppPieModal();
    });
    mask.querySelector('#dash-app-pie-close')?.addEventListener('click', closeAppPieModal);
  }

  function appsChartHtml(apps) {
    appsData = Array.isArray(apps) ? apps.slice() : [];
    if (!appsData.length) {
      return `
        <section class="panel dash-panel" id="dash-apps-panel">
          <div class="panel-header"><h3>应用安装</h3></div>
          <div class="panel-body text-muted" style="padding:32px;text-align:center">暂无应用数据</div>
        </section>`;
    }
    const sorted = appsData.slice().sort((a, b) =>
      appCoverageRate(b) - appCoverageRate(a) ||
      (Number(b.install_count) || 0) - (Number(a.install_count) || 0)
    );
    const cards = sorted.map(a => {
      const rate = appCoverageRate(a);
      const verCount = Array.isArray(a.versions) ? a.versions.length : (Number(a.version_count) || 0);
      return `<button type="button" class="dash-app-card" data-app-id="${esc(a.id)}">
        <div class="dash-app-card-top">
          <div class="dash-app-card-title">${esc(a.app_name || '—')}</div>
          <div class="dash-app-card-rate">${rate}<em>%</em></div>
        </div>
        <div class="dash-app-card-bar" aria-hidden="true"><i style="width:${rate}%"></i></div>
        <div class="dash-app-card-kpis">
          <div><b>${fmt(a.install_count)}</b><span>已安装</span></div>
          <div><b>${fmt(a.not_installed_count)}</b><span>未安装</span></div>
          <div><b>${fmt(verCount)}</b><span>版本</span></div>
        </div>
        <div class="dash-app-card-foot">点击查看版本构成 ›</div>
      </button>`;
    }).join('');

    return `
      <section class="panel dash-panel" id="dash-apps-panel">
        <div class="panel-header">
          <h3>应用安装</h3>
          <a class="extra btn-link" href="${U.href('apps')}">应用管理</a>
        </div>
        <div class="panel-body">
          <div class="dash-app-hint">按覆盖率排序 · 点击卡片查看版本饼图</div>
          <div class="dash-app-grid" id="dash-apps-list">${cards}</div>
        </div>
      </section>`;
  }

  function bindAppsChart() {
    const panel = document.getElementById('dash-apps-panel');
    if (!panel) return;
    panel.querySelectorAll('.dash-app-card').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-app-id');
        const app = appsData.find(a => String(a.id) === String(id));
        if (app) openAppPieModal(app);
      });
    });
  }

  function renderContent(data) {
    const devices = (data && data.devices) || {};
    const apps = (data && data.apps) || [];
    orgTree = Array.isArray(data && data.org) ? data.org : [];
    orgPath = [];
    return `
      <div class="dash-page">
        ${devicePanelHtml(devices)}
        ${orgChartShellHtml()}
        ${appsChartHtml(apps)}
      </div>`;
  }

  MDMLayout.mount({
    pageId: 'dashboard',
    title: '数据看板',
    content: `<div id="dash-root"><div class="panel"><div class="panel-body text-muted" style="padding:40px;text-align:center">加载中…</div></div></div>`,
    onMount() {
      const root = document.getElementById('dash-root');
      if (!root) return;
      MDMApi.getDashboardOverview()
        .then(data => {
          root.innerHTML = renderContent(data);
          bindOrgChart();
          bindAppsChart();
        })
        .catch(e => {
          root.innerHTML = `<div class="panel"><div class="panel-body text-muted" style="padding:40px;text-align:center">${esc(e.message || '加载失败')}</div></div>`;
        });
    }
  });
})();
