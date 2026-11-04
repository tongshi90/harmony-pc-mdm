window.MDMUtils = {
  fmt: n => Number(n).toLocaleString('zh-CN'),

  /** 统一默认应用图标（未上传时共用） */
  DEFAULT_APP_ICON: '/assets/img/app-default.svg',
  /** HAP 安装包展示图标 */
  HAP_PACKAGE_ICON: '/assets/img/hap-package.svg?v=2',

  fmtFileSize(n) {
    if (n == null || n === '') return '';
    const num = Number(n);
    if (!Number.isFinite(num) || num < 0) return '';
    if (num < 1024) return `${num} B`;
    if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
    return `${(num / 1024 / 1024).toFixed(2)} MB`;
  },

  /**
   * 应用图标展示 HTML。
   * @param {{ app_icon?: string, has_icon?: boolean, app_name?: string }} app
   * @param {{ size?: number, className?: string }} [opts]
   */
  appIconHtml(app, opts = {}) {
    const size = opts.size || 44;
    const cls = opts.className || 'app-icon';
    const src = (app && app.has_icon && app.app_icon)
      ? app.app_icon
      : this.DEFAULT_APP_ICON;
    const alt = (app && app.app_name) ? String(app.app_name) : '应用';
    return `<img class="${cls}" src="${src}" alt="${this.escapeAttr(alt)}" width="${size}" height="${size}" loading="lazy">`;
  },

  query(key) {
    return new URLSearchParams(window.location.search).get(key);
  },

  /**
   * 与 components.css `.card-grid` 媒体查询对齐的列数。
   * @param {'default'|'cols-4'} [variant='default'] default=应用等一行最多5；cols-4=管理员/角色一行最多4
   */
  cardGridCols(variant = 'default') {
    const w = window.innerWidth || 1440;
    if (w <= 768) return 1;
    if (w <= 900) return 2;
    if (variant === 'cols-4') {
      if (w <= 1200) return 3;
      return 4;
    }
    if (w <= 1200) return 3;
    if (w <= 1400) return 4;
    return 5;
  },

  /**
   * 卡片列表分页条数：按当前列数铺满整行（默认 3 行；单列至少 6 条）。
   * @param {'default'|'cols-4'} [variant='default']
   * @param {number} [rows=3]
   */
  cardGridPageSize(variant = 'default', rows = 3) {
    const cols = this.cardGridCols(variant);
    return cols === 1 ? Math.max(6, rows) : cols * rows;
  },

  /**
   * 窗口缩放时若卡片分页条数变化则回调（已防抖）。
   * @param {'default'|'cols-4'} variant
   * @param {() => number} getPageSize
   * @param {(next: number, prev: number) => void} onChange
   * @returns {() => void} 取消监听
   */
  bindCardGridPageResize(variant, getPageSize, onChange) {
    let timer = null;
    const handler = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const prev = getPageSize();
        const next = this.cardGridPageSize(variant);
        if (next === prev) return;
        onChange(next, prev);
      }, 200);
    };
    window.addEventListener('resize', handler);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', handler);
    };
  },

  badgeStatus(status) {
    const map = {
      online: '<span class="badge badge-ok">在线</span>',
      offline: '<span class="badge badge-off">离线</span>',
      compliant: '<span class="badge badge-ok">合规</span>',
      'non-compliant': '<span class="badge badge-fail">不合规</span>',
      active: '<span class="badge badge-ok">启用</span>',
      disabled: '<span class="badge badge-off">禁用</span>',
      published: '<span class="badge badge-ok">已发布</span>',
      draft: '<span class="badge badge-off">草稿</span>',
      completed: '<span class="badge badge-ok">已完成</span>',
      dispatched: '<span class="badge badge-ok">已下发</span>',
      running: '<span class="tag tag-blue">进行中</span>',
      partial: '<span class="tag tag-orange">部分失败</span>',
      failed: '<span class="badge badge-fail">失败</span>',
      success: '<span class="badge badge-ok">成功</span>',
      skipped: '<span class="badge badge-off">已跳过</span>',
      pending: '<span class="badge badge-off">待执行</span>',
      matched: '<span class="badge badge-ok">匹配</span>',
      mismatched: '<span class="badge badge-fail">不匹配</span>',
      queued: '<span class="badge badge-off">暂存</span>',
      staged: '<span class="badge badge-off">暂存</span>',
      pending_dispatch: '<span class="tag tag-blue">待下发</span>',
      pending_notify: '<span class="badge badge-off">暂存</span>',
      notified: '<span class="tag tag-blue">待下发</span>',
      executing: '<span class="tag tag-blue">执行中</span>',
      timeout: '<span class="badge badge-fail">超时</span>'
    };
    return map[status] || `<span class="badge badge-off">${status}</span>`;
  },

  alertTag(level) {
    const labels = { critical: '严重', warning: '警告', info: '信息' };
    return `<span class="alert-tag ${level}">${labels[level] || level}</span>`;
  },

  toast(msg, type = 'success') {
    let wrap = document.querySelector('.toast-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'toast-wrap';
      document.body.appendChild(wrap);
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => el.remove(), 2800);
  },

  confirm(msg, onOk) {
    // 使用独立 class，避免命中页面内其它带 modal-mask 的业务弹窗（如成员导入）
    let mask = document.querySelector('.confirm-modal-mask');
    if (!mask) {
      mask = document.createElement('div');
      mask.className = 'modal-mask confirm-modal-mask';
      mask.innerHTML = `<div class="modal"><div class="modal-header">确认操作</div><div class="modal-body"></div><div class="modal-footer"><button class="btn modal-cancel">取消</button><button class="btn btn-primary modal-ok">确定</button></div></div>`;
      document.body.appendChild(mask);
    }
    mask.querySelector('.modal-body').textContent = msg;
    mask.classList.add('show');
    const close = () => mask.classList.remove('show');
    mask.querySelector('.modal-cancel').onclick = close;
    mask.querySelector('.modal-ok').onclick = () => { close(); onOk && onOk(); };
  },

  /**
   * 通用表单/详情弹窗：onOk 返回 false 可阻止关闭；size: sm | md | lg | xl
   * showCancel：未传时，有 onOk 显示「取消」（确认/表单），无 onOk 视为只读详情仅保留主按钮。
   */
  modal({ title, body, okText = '确定', onOk, size = 'lg', showCancel } = {}) {
    let mask = document.querySelector('.form-modal-mask');
    if (!mask) {
      mask = document.createElement('div');
      mask.className = 'modal-mask form-modal-mask';
      mask.innerHTML = `<div class="modal modal-lg"><div class="modal-header"></div><div class="modal-body"></div><div class="modal-footer"><button class="btn modal-cancel">取消</button><button class="btn btn-primary modal-ok">确定</button></div></div>`;
      document.body.appendChild(mask);
    }
    const box = mask.querySelector('.modal');
    if (box) {
      const sizeClass =
        size === 'sm' ? 'modal-sm'
          : size === 'md' ? 'modal-md'
            : size === 'xl' ? 'modal-xl'
              : 'modal-lg';
      box.className = `modal ${sizeClass}`;
    }
    mask.querySelector('.modal-header').textContent = title || '';
    mask.querySelector('.modal-body').innerHTML = body || '';
    const okBtn = mask.querySelector('.modal-ok');
    const cancelBtn = mask.querySelector('.modal-cancel');
    okBtn.textContent = okText;
    const cancelVisible =
      showCancel !== undefined ? !!showCancel : typeof onOk === 'function';
    cancelBtn.style.display = cancelVisible ? '' : 'none';
    mask.classList.add('show');
    const close = () => mask.classList.remove('show');
    cancelBtn.onclick = close;
    okBtn.onclick = async () => {
      if (!onOk) { close(); return; }
      const ret = await onOk();
      if (ret !== false) close();
    };
  },

  _prettyJson(raw) {
    if (raw == null || raw === '') return '—';
    if (typeof raw === 'object') {
      try { return JSON.stringify(raw, null, 2); } catch { return String(raw); }
    }
    const text = String(raw);
    try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; }
  },

  _escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  },

  showAuditLogDetail(log) {
    let mask = document.querySelector('.audit-log-modal-mask');
    if (!mask) {
      mask = document.createElement('div');
      mask.className = 'modal-mask audit-log-modal-mask';
      mask.innerHTML = `<div class="modal modal-lg">
        <div class="modal-header">操作日志详情</div>
        <div class="modal-body audit-log-modal-body"></div>
        <div class="modal-footer"><button class="btn btn-primary audit-log-close">关闭</button></div>
      </div>`;
      document.body.appendChild(mask);
      mask.querySelector('.audit-log-close').onclick = () => mask.classList.remove('show');
    }
    const body = mask.querySelector('.audit-log-modal-body');
    const esc = (v) => this._escapeHtml(v);
    const operator = log.user_name || log.username || log.user || '—';
    const time = log.create_time || log.time || '—';
    const success = log.success === 1 || log.success === true || log.status === 'success';
    const queryPart = log.query_params
      ? `<div class="json-preview-label">Query 参数</div><pre class="json-preview">${esc(this._prettyJson(log.query_params))}</pre>`
      : '';
    const req = log.request_body != null ? log.request_body : log.request;
    const res = log.response_body != null ? log.response_body : log.response;
    body.innerHTML = `
      <table class="kv-table" style="margin-bottom:16px"><tbody>
        <tr><th>操作时间</th><td>${esc(time)}</td></tr>
        <tr><th>操作人</th><td>${esc(operator)}${log.username && log.user_name ? ` <span class="text-muted">(${esc(log.username)})</span>` : ''}</td></tr>
        <tr><th>动作</th><td>${esc(log.action || '—')}</td></tr>
        <tr><th>所属模块</th><td>${esc(log.module || '—')}</td></tr>
        <tr><th>请求方式</th><td>${esc(log.method || '—')} <code>${esc(log.path || '')}</code></td></tr>
        <tr><th>客户端 IP</th><td><code>${esc(log.client_ip || log.ip || '—')}</code></td></tr>
        <tr><th>耗时</th><td>${log.duration_ms != null ? log.duration_ms + ' ms' : esc(log.duration || '—')}</td></tr>
        <tr><th>执行结果</th><td>${this.badgeStatus(success ? 'success' : 'failed')}${log.response_code != null ? ` · code=${esc(log.response_code)}` : ''}</td></tr>
      </tbody></table>
      ${queryPart}
      <div class="json-preview-label"${queryPart ? ' style="margin-top:12px"' : ''}>请求体 <span>Body</span></div>
      <pre class="json-preview">${esc(this._prettyJson(req))}</pre>
      <div class="json-preview-label" style="margin-top:12px">返回体 <span>Response</span></div>
      <pre class="json-preview">${esc(this._prettyJson(res))}</pre>`;
    mask.classList.add('show');
  },

  bindSave(selector, msg) {
    document.querySelectorAll(selector).forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        MDMUtils.toast(msg || '已保存');
      });
    });
  },

  lineChart(container, data, key, color) {
    if (!container) return;
    const w = 500, h = 190, pad = { t: 14, r: 14, b: 26, l: 36 };
    const vals = data.map(d => d[key]);
    const max = Math.max(...vals) * 1.08;
    const min = Math.min(...vals) * 0.92;
    const range = max - min || 1;
    const pts = data.map((d, i) => {
      const x = pad.l + (i / (data.length - 1)) * (w - pad.l - pad.r);
      const y = pad.t + (1 - (d[key] - min) / range) * (h - pad.t - pad.b);
      return `${x},${y}`;
    }).join(' ');
    const area = pts + ` ${pad.l + (w - pad.l - pad.r)},${h - pad.b} ${pad.l},${h - pad.b}`;
    container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      ${data.map((d, i) => `<text x="${pad.l + (i / (data.length - 1)) * (w - pad.l - pad.r)}" y="${h - 6}" text-anchor="middle" fill="var(--text-secondary)" font-size="10">${d.date}</text>`).join('')}
      <polygon points="${area}" fill="${color}" opacity="0.1"/>
      <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
      ${data.map((d, i) => {
        const x = pad.l + (i / (data.length - 1)) * (w - pad.l - pad.r);
        const y = pad.t + (1 - (d[key] - min) / range) * (h - pad.t - pad.b);
        return `<circle cx="${x}" cy="${y}" r="3" fill="${color}"/>`;
      }).join('')}
    </svg>`;
  },

  initTabs(container) {
    if (!container) return;
    const tabs = container.querySelectorAll('.tab-item');
    const panels = container.querySelectorAll('.tab-panel');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        const panel = container.querySelector(`[data-panel="${tab.dataset.tab}"]`);
        if (panel) panel.classList.add('active');
      });
    });
  },

  initFilterTags(container) {
    if (!container) return;
    container.querySelectorAll('.filter-tag').forEach(tag => {
      tag.addEventListener('click', () => {
        container.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
        tag.classList.add('active');
      });
    });
  },

  pagination(total, page = 1, pageSize = 10, opts = {}) {
    const unit = opts.unit || '条';
    const pageItems = opts.pageItems != null ? opts.pageItems : Math.min(pageSize, total);
    const pages = Math.max(1, Math.ceil(total / pageSize) || 1);
    const cur = Math.min(Math.max(1, page), pages);

    // 始终保留：首页、当前附近、末两页，中间缺口用省略号，避免只能连点翻页
    const pick = new Set([1, pages]);
    if (pages >= 2) pick.add(pages - 1);
    for (let p = cur - 2; p <= cur + 2; p++) {
      if (p >= 1 && p <= pages) pick.add(p);
    }
    const sorted = Array.from(pick).sort((a, b) => a - b);
    const parts = [];
    let prev = 0;
    sorted.forEach(p => {
      if (prev && p - prev > 1) {
        parts.push('<span class="page-ellipsis" aria-hidden="true">…</span>');
      }
      parts.push(`<span class="page-btn${p === cur ? ' active' : ''}" data-page="${p}">${p}</span>`);
      prev = p;
    });

    return `<div class="pagination"><span>共 ${total} ${unit} · 本页 ${pageItems} ${unit}</span>
      ${parts.join('')}</div>`;
  },

  /**
   * 轻量日期选择器（按天）。root 需含 .date-picker-trigger / .date-picker-panel / input[type=hidden]
   * @returns {{ getValue: () => string, setValue: (v: string) => void, close: () => void }}
   */
  bindDatePicker(root, opts = {}) {
    if (!root) return null;
    const trigger = root.querySelector('.date-picker-trigger');
    const textEl = root.querySelector('.date-picker-trigger-text');
    const panel = root.querySelector('.date-picker-panel');
    const hidden = root.querySelector('input[type="hidden"]');
    const placeholder = opts.placeholder || '选择日期';
    const WEEK = ['日', '一', '二', '三', '四', '五', '六'];

    let viewYear = new Date().getFullYear();
    let viewMonth = new Date().getMonth();
    let value = (hidden && hidden.value) || opts.value || '';

    function pad(n) {
      return String(n).padStart(2, '0');
    }
    function fmt(y, m, d) {
      return `${y}-${pad(m + 1)}-${pad(d)}`;
    }
    function parse(v) {
      const m = String(v || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!m) return null;
      return { y: Number(m[1]), m: Number(m[2]) - 1, d: Number(m[3]) };
    }
    function syncTrigger() {
      if (!textEl) return;
      if (value) {
        textEl.textContent = value;
        textEl.classList.remove('is-placeholder');
      } else {
        textEl.textContent = placeholder;
        textEl.classList.add('is-placeholder');
      }
      if (hidden) hidden.value = value;
    }
    function placePanel() {
      if (!panel || !trigger || panel.hidden) return;
      // 挂到 body，避免被 .panel overflow:hidden 裁切
      if (panel.parentElement !== document.body) {
        document.body.appendChild(panel);
      }
      const rect = trigger.getBoundingClientRect();
      const panelW = panel.offsetWidth || 260;
      const panelH = panel.offsetHeight || 300;
      const gap = 4;
      let top = rect.bottom + gap;
      let left = rect.left;
      // 下方空间不足时向上展开
      if (top + panelH > window.innerHeight - 8 && rect.top - gap - panelH > 8) {
        top = rect.top - gap - panelH;
      }
      // 右侧超出视口时左移
      if (left + panelW > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - panelW - 8);
      }
      if (left < 8) left = 8;
      if (top < 8) top = 8;
      panel.style.top = `${Math.round(top)}px`;
      panel.style.left = `${Math.round(left)}px`;
    }
    function restorePanel() {
      if (!panel) return;
      panel.hidden = true;
      panel.style.top = '';
      panel.style.left = '';
      if (panel.parentElement === document.body) {
        root.appendChild(panel);
      }
    }
    function closeOtherPickers() {
      document.querySelectorAll('.date-picker.is-open').forEach(el => {
        if (el === root) return;
        el.classList.remove('is-open');
        const p = el.querySelector('.date-picker-panel')
          || document.querySelector(`.date-picker-panel[data-owner="${el.id}"]`);
        if (p) {
          p.hidden = true;
          p.style.top = '';
          p.style.left = '';
          if (p.parentElement === document.body && el) el.appendChild(p);
        }
      });
      // 已挪到 body 的面板用 data-owner 关联
      document.querySelectorAll('.date-picker-panel[data-owner]').forEach(p => {
        const ownerId = p.getAttribute('data-owner');
        if (!ownerId || ownerId === root.id) return;
        const owner = document.getElementById(ownerId);
        if (!owner || owner.classList.contains('is-open')) return;
        p.hidden = true;
        p.style.top = '';
        p.style.left = '';
        if (p.parentElement === document.body) owner.appendChild(p);
        owner.classList.remove('is-open');
      });
    }
    function close() {
      root.classList.remove('is-open');
      restorePanel();
    }
    function open() {
      closeOtherPickers();
      const hit = parse(value);
      if (hit) {
        viewYear = hit.y;
        viewMonth = hit.m;
      }
      if (root.id) panel?.setAttribute('data-owner', root.id);
      root.classList.add('is-open');
      if (panel) panel.hidden = false;
      renderPanel();
      placePanel();
    }
    function renderPanel() {
      if (!panel) return;
      const first = new Date(viewYear, viewMonth, 1);
      const startWeek = first.getDay();
      const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
      const prevDays = new Date(viewYear, viewMonth, 0).getDate();
      const today = new Date();
      const todayKey = fmt(today.getFullYear(), today.getMonth(), today.getDate());
      const cells = [];
      for (let i = 0; i < 42; i++) {
        let y = viewYear;
        let m = viewMonth;
        let d;
        let muted = false;
        if (i < startWeek) {
          d = prevDays - startWeek + i + 1;
          m -= 1;
          muted = true;
          if (m < 0) { m = 11; y -= 1; }
        } else if (i - startWeek + 1 > daysInMonth) {
          d = i - startWeek + 1 - daysInMonth;
          m += 1;
          muted = true;
          if (m > 11) { m = 0; y += 1; }
        } else {
          d = i - startWeek + 1;
        }
        const key = fmt(y, m, d);
        const cls = [
          'date-picker-day',
          muted ? 'is-muted' : '',
          key === todayKey ? 'is-today' : '',
          key === value ? 'is-selected' : ''
        ].filter(Boolean).join(' ');
        cells.push(`<button type="button" class="${cls}" data-date="${key}">${d}</button>`);
      }
      panel.innerHTML = `
        <div class="date-picker-head">
          <button type="button" class="date-picker-nav" data-nav="-1" aria-label="上个月">‹</button>
          <span class="date-picker-head-title">${viewYear} 年 ${viewMonth + 1} 月</span>
          <button type="button" class="date-picker-nav" data-nav="1" aria-label="下个月">›</button>
        </div>
        <div class="date-picker-week">${WEEK.map(w => `<span>${w}</span>`).join('')}</div>
        <div class="date-picker-days">${cells.join('')}</div>
        <div class="date-picker-foot">
          <button type="button" class="btn-link" data-clear>清除</button>
        </div>`;
      panel.querySelectorAll('[data-nav]').forEach(btn => {
        btn.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          const delta = Number(btn.getAttribute('data-nav') || 0);
          viewMonth += delta;
          if (viewMonth < 0) { viewMonth = 11; viewYear -= 1; }
          if (viewMonth > 11) { viewMonth = 0; viewYear += 1; }
          renderPanel();
          placePanel();
        });
      });
      panel.querySelectorAll('.date-picker-day').forEach(btn => {
        btn.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          value = btn.getAttribute('data-date') || '';
          syncTrigger();
          close();
          if (typeof opts.onChange === 'function') opts.onChange(value);
        });
      });
      panel.querySelector('[data-clear]')?.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        value = '';
        syncTrigger();
        close();
        if (typeof opts.onChange === 'function') opts.onChange(value);
      });
    }

    trigger?.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      if (root.classList.contains('is-open')) close();
      else open();
    });
    panel?.addEventListener('click', e => e.stopPropagation());
    if (!document.documentElement.dataset.datePickerDocBound) {
      document.documentElement.dataset.datePickerDocBound = '1';
      const closeAllDatePickers = () => {
        document.querySelectorAll('.date-picker.is-open').forEach(el => {
          el.classList.remove('is-open');
        });
        document.querySelectorAll('.date-picker-panel').forEach(p => {
          p.hidden = true;
          p.style.top = '';
          p.style.left = '';
          const ownerId = p.getAttribute('data-owner');
          const owner = ownerId ? document.getElementById(ownerId) : null;
          if (owner && p.parentElement === document.body) owner.appendChild(p);
        });
      };
      document.addEventListener('click', closeAllDatePickers);
      window.addEventListener('resize', closeAllDatePickers);
      window.addEventListener('scroll', closeAllDatePickers, true);
    }

    syncTrigger();
    return {
      getValue: () => value,
      setValue: (v) => {
        value = v || '';
        const hit = parse(value);
        if (hit) {
          viewYear = hit.y;
          viewMonth = hit.m;
        }
        syncTrigger();
      },
      close
    };
  },

  findDevice() {
    return null;
  },

  findProduct() {
    return null;
  },

  findApp() {
    return null;
  },

  findTask() {
    return null;
  },

  findCommand(code) {
    const list = MDM.policyCommands || MDM.commands || [];
    const key = String(code || '').trim();
    if (!key) return null;
    const hit = list.find(c => c.code === key || c.protocolCode === key);
    if (hit) return hit;
    // 旧种子 / 历史数据：PASSWORD_POLICY → PSW_MANAGEMENT
    if (key === 'PASSWORD_POLICY') {
      return list.find(c => c.code === 'PSW_MANAGEMENT' || c.protocolCode === 'PSW_MANAGEMENT') || null;
    }
    // 未命中时不得回退到 list[0]（否则会全部显示成「Wifi配置」）
    return null;
  },

  /** 归一化历史策略 Code（入库/展示用） */
  normalizePolicyCode(code) {
    const key = String(code || '').trim();
    if (key === 'PASSWORD_POLICY') return 'PSW_MANAGEMENT';
    return key;
  },

  /**
   * 策略项摘要（与后端 app.utils.policy_summary 对齐）。
   * 编辑草稿未入库时用；已入库优先用接口返回的 summary。
   */
  policyItemSummary(policyCode, param) {
    const code = String(policyCode || '').trim();
    const p = param && typeof param === 'object' ? param : {};
    const list = (v) => (Array.isArray(v) ? v : []);
    const firstLabel = (items) => {
      for (const it of items) {
        if (it && typeof it === 'object') {
          for (const k of ['name', 'app_name', 'appName', 'bundleName', 'appId', 'id']) {
            if (it[k] != null && String(it[k]).trim()) return String(it[k]).trim();
          }
        } else if (it != null && String(it).trim()) {
          return String(it).trim();
        }
      }
      return '';
    };
    const remoteOps = {
      lockDevice: '锁定', unlockDevice: '解除锁定'
    };
    const locationMap = {
      DEFAULT: '定位由用户自行开关',
      DISALLOW: '禁止定位',
      FORCE_OPEN: '强制开启定位'
    };
    const usbMap = {
      READ_WRITE: 'U盘设为可读可写',
      READ_ONLY: 'U盘设为只读',
      DISABLED: '禁用 U盘'
    };

    if (code === 'WIFI_SET') {
      const ssid = String(p.ssid || '').trim();
      return ssid ? `连接「${ssid}」Wifi` : '清空 Wifi 的自动连接';
    }
    if (code === 'REMOTE_CONTROL') {
      const label = remoteOps[String(p.operationType || '').trim()];
      return label ? `对设备执行${label}` : '清空远程操控指令';
    }
    if (code === 'LOCATION_POLICY') {
      return locationMap[String(p.policyType || '').trim()] || '清空定位限制';
    }
    if (code === 'APP_MANAGEMENT') {
      const installs = list(p.currentApps);
      const uninstalls = list(p.uninstallApps);
      const n = installs.length;
      const u = uninstalls.length;
      if (!n && !u) return '清空静默安装和卸载';
      const parts = [];
      if (n) {
        const name = firstLabel(installs);
        if (n === 1 && name) parts.push(`安装「${name}」应用`);
        else if (name) parts.push(`安装「${name}」等${n}个应用`);
        else parts.push(`安装${n}个应用`);
      }
      if (u) {
        const name = firstLabel(uninstalls);
        if (u === 1 && name) parts.push(`卸载「${name}」应用`);
        else if (name) parts.push(`卸载「${name}」等${u}个应用`);
        else parts.push(`卸载${u}个应用`);
      }
      if (n && u) return `${parts[0]}，并${parts[1]}`;
      return parts[0] || '清空静默安装和卸载';
    }
    if (code === 'APP_CONFIG_MANAGEMENT') {
      const a = list(p.allowAppIds).length;
      const d = list(p.disallowAppIds).length;
      const f = list(p.disallowedUninstallAppIds).length;
      if (!a && !d && !f) return '清空应用安装与卸载限制';
      return `允许安装${a}个、禁止安装${d}个、禁止卸载${f}个应用`;
    }
    if (code === 'DOMAIN_MANAGEMENT') {
      const domains = list(p.domainNames).map(x => String(x || '').trim()).filter(Boolean);
      if (!domains.length) return '清空网站访问限制';
      if (domains.length === 1) return `禁止访问「${domains[0]}」`;
      return `禁止访问「${domains[0]}」等${domains.length}个网站`;
    }
    if (code === 'FIREWALL_MANAGEMENT') {
      const n = list(p.firewalls).length;
      return n ? `设置 ${n} 条防火墙拦截规则` : '清空防火墙规则';
    }
    if (code === 'PSW_MANAGEMENT' || code === 'PASSWORD_POLICY') {
      let days = null;
      if (p.validityPeriod != null && p.validityPeriod !== '') {
        const n = Number(p.validityPeriod);
        if (Number.isFinite(n)) days = n > 100000 ? Math.max(1, Math.floor(n / 86400000)) : n;
      }
      const desc = String(p.additionalDescription || '').trim();
      const regex = String(p.complexityRegex || '').trim();
      if (days != null) return `开机密码有效期 ${days} 天`;
      if (desc) return `开机密码要求：${desc.length > 20 ? `${desc.slice(0, 20)}…` : desc}`;
      if (regex) return '已配置开机密码规则';
      return '清空开机密码规则';
    }
    if (code === 'USB_MANAGEMENT') {
      return usbMap[String(p.usbPolicy || '').trim()] || '清空 U盘使用限制';
    }
    if (!Object.keys(p).length) return '已添加策略项';
    return '已配置策略参数';
  },

  /** 展示用：优先入库 summary，否则按 param 现场组装 */
  displayPolicyItemSummary(item) {
    if (!item) return '—';
    const stored = String(item.summary || '').trim();
    if (stored) return stored;
    return this.policyItemSummary(item.policy_code, item.param || {});
  },

  /** 快照展示时隐藏的字段（如 Wi-Fi 证书 Base64 无法还原文件名） */
  _isSnapshotHiddenKey(key) {
    return String(key || '').trim() === 'certEntry';
  },

  /** 从应用目录解析展示用应用名（不暴露 App ID / 包名给操作员） */
  resolveAppDisplayName(ref) {
    const catalog = this._appInstallCatalog || {};
    const all = []
      .concat(catalog.allApps || [])
      .concat(catalog.selectable || []);
    if (typeof ref === 'string') {
      const s = String(ref).trim();
      if (!s) return '';
      const hit = all.find(a => a && (a.bundleName === s || a.appId === s || String(a.id) === s));
      return (hit && hit.name) ? String(hit.name).trim() : '';
    }
    if (ref && typeof ref === 'object') {
      const direct = String(ref.appName || ref.app_name || ref.name || '').trim();
      if (direct) return direct;
      const appId = String(ref.appId || '').trim();
      const bundle = String(ref.bundleName || ref.bundle_name || '').trim();
      const hit = all.find(a => a && (
        (appId && a.appId === appId) || (bundle && a.bundleName === bundle)
      ));
      return (hit && hit.name) ? String(hit.name).trim() : '';
    }
    return '';
  },

  _paramDefByKey(policyCode, key) {
    const cmd = this.findCommand(this.normalizePolicyCode(policyCode));
    if (!cmd || !Array.isArray(cmd.params)) return null;
    const k = String(key || '').trim();
    return cmd.params.find(p => p && p.key === k) || null;
  },

  _fieldTitle(policyCode, key) {
    const def = this._paramDefByKey(policyCode, key);
    if (def) return this.paramUserTitle(def);
    const fallback = {
      installedApps: '设备已安装应用',
      appId: 'App ID',
      appName: '应用名称',
      bundleName: '包名',
      version: '版本',
      versionCode: '版本号',
      bundleDownloadUrl: '下载地址',
      srcAddr: '来源地址',
      destAddr: '目标地址',
      srcPort: '来源端口',
      destPort: '目标端口'
    };
    return fallback[key] || key || '—';
  },

  /**
   * 将策略 param 中的单个值格式化为操作人员可读文案（枚举中文、天/毫秒换算等）。
   * 返回纯文本；隐藏字段返回 null。
   */
  formatPolicyValueText(policyCode, key, value) {
    if (this._isSnapshotHiddenKey(key)) return null;
    if (value == null || value === '') return '无';

    const def = this._paramDefByKey(policyCode, key);
    const type = def && def.type;

    if (type === 'days_ms' || key === 'validityPeriod') {
      const n = Number(value);
      if (!Number.isFinite(n)) return String(value);
      const days = n >= 86400000 ? Math.max(1, Math.round(n / 86400000)) : n;
      return `${days} 天`;
    }

    if (type === 'enum' && def && def.options) {
      const opts = this.normalizeEnumOptions(def.options);
      const hit = opts.find(o => String(o.value) === String(value));
      if (hit) return this.enumOptionLabel(hit, true);
    }

    if (type === 'file') return null;

    if (Array.isArray(value)) {
      if (!value.length) return '（空）';
      if (key === 'domainNames' || type === 'array_string') {
        return value.map(x => String(x || '').trim()).filter(Boolean).join('、') || '（空）';
      }
      if (key === 'uninstallApps') {
        // 预期里存的是 bundleName，展示时解析为应用名
        return value.map((x) => {
          const name = this.resolveAppDisplayName(x);
          return name || '';
        }).filter(Boolean).join('、') || '（空）';
      }
      if (key === 'currentApps') {
        // 需要安装：应用名 + 配置的版本号
        return value.map((it, i) => {
          if (!it || typeof it !== 'object') {
            const name = this.resolveAppDisplayName(it);
            return name || '';
          }
          const name = this.resolveAppDisplayName(it) || `应用${i + 1}`;
          const ver = String(it.version || it.version_name || '').trim();
          return ver ? `${name}（${ver}）` : name;
        }).filter(Boolean).join('、') || '（空）';
      }
      if (key === 'installedApps') {
        // 当前已装：只展示应用名
        return value.map((it, i) => {
          const name = this.resolveAppDisplayName(it);
          return name || (it && typeof it === 'object' ? `应用${i + 1}` : '');
        }).filter(Boolean).join('、') || '（空）';
      }
      if (key === 'allowAppIds' || key === 'disallowAppIds' || key === 'disallowedUninstallAppIds'
          || type === 'app_multi_select') {
        // 应用配置管理：只展示应用名
        return value.map((it) => this.resolveAppDisplayName(it)).filter(Boolean).join('、') || '（空）';
      }
      if (key === 'firewalls' || type === 'firewall_rules') {
        return value.map((rule, i) => {
          if (!rule || typeof rule !== 'object') return `规则${i + 1}`;
          const parts = [];
          if (rule.srcAddr) parts.push(`源 ${rule.srcAddr}`);
          if (rule.srcPort) parts.push(`源端口 ${rule.srcPort}`);
          if (rule.destAddr) parts.push(`目标 ${rule.destAddr}`);
          if (rule.destPort) parts.push(`目标端口 ${rule.destPort}`);
          return `规则${i + 1}：${parts.join('，') || '无'}`;
        }).join('；');
      }
      try {
        return JSON.stringify(value);
      } catch (_) {
        return String(value);
      }
    }

    if (typeof value === 'boolean') return value ? '是' : '否';
    if (typeof value === 'object') {
      try {
        return JSON.stringify(value);
      } catch (_) {
        return String(value);
      }
    }
    return String(value);
  },

  /**
   * 策略 param → 可读 HTML（字段中文名 + 可读值），供设备快照等展示。
   * 与设置页同一套标题/枚举释义，不追求样式一致。
   */
  formatPolicyParamHtml(policyCode, param) {
    const code = this.normalizePolicyCode(policyCode);
    const p = param && typeof param === 'object' && !Array.isArray(param) ? param : {};
    const cmd = this.findCommand(code);
    const rows = [];
    const seen = new Set();

    const pushRow = (key, val) => {
      if (this._isSnapshotHiddenKey(key) || seen.has(key)) return;
      const text = this.formatPolicyValueText(code, key, val);
      if (text == null) return;
      seen.add(key);
      rows.push({
        title: this._fieldTitle(code, key),
        text
      });
    };

    if (cmd && Array.isArray(cmd.params)) {
      cmd.params.forEach(def => {
        if (!def || !def.key) return;
        if (!(def.key in p)) return;
        pushRow(def.key, p[def.key]);
      });
    }
    Object.keys(p).forEach(key => {
      if (seen.has(key)) return;
      pushRow(key, p[key]);
    });

    if (!rows.length) {
      return '<span class="text-muted">无配置内容</span>';
    }
    return `<dl class="snap-param-list">${rows.map(r => `
      <div class="snap-param-row">
        <dt>${this.escapeAttr(r.title)}</dt>
        <dd>${this.escapeAttr(r.text)}</dd>
      </div>`).join('')}</dl>`;
  },

  /** 差异字段路径 → 可读说明（如 validityPeriod → 密码有效期（天）） */
  formatPolicyDiffFieldHtml(policyCode, fieldDiff) {
    const f = fieldDiff || {};
    const path = String(f.path || '').trim() || '$';
    const topKey = path.replace(/\[.*?\]/g, '').split('.')[0] || path;
    if (this._isSnapshotHiddenKey(topKey) || this._isSnapshotHiddenKey(path)) {
      return '';
    }
    const title = this._fieldTitle(policyCode, topKey);
    const exp = this.formatPolicyValueText(policyCode, topKey, f.expected);
    const cur = this.formatPolicyValueText(policyCode, topKey, f.current);
    if (exp == null && cur == null) return '';
    const left = exp == null ? '无' : exp;
    const right = cur == null ? '无' : cur;
    return `<div class="snap-diff-line"><span class="snap-diff-label">${this.escapeAttr(title)}</span>
      <span class="snap-diff-vals">${this.escapeAttr(left)} → <em>${this.escapeAttr(right)}</em></span></div>`;
  },

  aggregatePolicySummaries(summaries, limit) {
    const n = limit == null ? 3 : limit;
    const cleaned = (summaries || []).map(s => String(s || '').trim()).filter(Boolean);
    if (!cleaned.length) return '—';
    if (cleaned.length <= n) return cleaned.join('；');
    return `${cleaned.slice(0, n).join('；')}；等${cleaned.length}项`;
  },

  /** 规范化枚举 options：支持逗号字符串或 [{value,label}] */
  normalizeEnumOptions(options) {
    if (!options) return [];
    if (Array.isArray(options)) {
      return options.map(o => {
        if (o && typeof o === 'object') {
          return { value: o.value != null ? String(o.value) : '', label: o.label || String(o.value) };
        }
        return { value: String(o), label: String(o) };
      });
    }
    return String(options).split(',').map(t => {
      const v = t.trim();
      return { value: v, label: v };
    });
  },

  escapeAttr(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  },

  findScene() {
    return null;
  },

  /** 策略所属分组：空 / 缺失 → 未分组 */
  sceneGroupId(scene) {
    if (!scene) return '';
    return scene.groupId || '';
  },

  findPolicyGroup() {
    return null;
  },

  policyGroupName(groupId) {
    if (!groupId) return '未分组';
    return '未分组';
  },

  /** 可选分组列表（不含「全部」） */
  policyGroupOptions() {
    return [];
  },

  countScenesInGroup(groupId, scenes) {
    const list = scenes || [];
    if (groupId === 'all') return list.length;
    if (groupId === 'ungrouped' || groupId === '') {
      return list.filter(s => !this.sceneGroupId(s)).length;
    }
    return list.filter(s => this.sceneGroupId(s) === groupId).length;
  },

  filterScenesByGroup(groupId, scenes) {
    const list = scenes || [];
    if (!groupId || groupId === 'all') return list.slice();
    if (groupId === 'ungrouped') return list.filter(s => !this.sceneGroupId(s));
    return list.filter(s => this.sceneGroupId(s) === groupId);
  },

  findSceneTask() {
    return null;
  },

  paramTypeLabel(type) {
    const map = {
      string: '字符串', number: '数字', long: '长整型', boolean: '布尔', enum: '枚举',
      array_string: '字符串数组', array_object: '对象数组', file: '证书/文件'
    };
    return map[type] || type;
  },

  /** 面向使用用户的字段标题（不展示协议字段名） */
  paramUserTitle(p) {
    if (!p) return '';
    if (p.title) return p.title;
    if (p.label && p.label !== p.key && !/^[A-Za-z][A-Za-z0-9_]*$/.test(p.label)) return p.label;
    if (p.desc) {
      const head = String(p.desc).split(/[。；;\n]/)[0].trim();
      if (head) return head.length > 40 ? head.slice(0, 40) + '…' : head;
    }
    return p.label || p.key || '';
  },

  /** 标题之外的补充说明（对齐标题时不重复） */
  paramUserHint(p) {
    if (!p || !p.desc) return '';
    const title = this.paramUserTitle(p);
    const desc = String(p.desc).trim();
    if (!desc || desc === title) return '';
    if (desc.startsWith(title)) {
      const rest = desc.slice(title.length).replace(/^[。；;，,\s]+/, '').trim();
      return rest;
    }
    return desc;
  },

  enumOptionLabel(o, userFacing) {
    if (!o) return '';
    if (userFacing) {
      const lab = (o.label || '').trim();
      if (lab) {
        // 下拉只展示简短中文释义
        const short = lab.split(/[。；;\n]/)[0].trim();
        return short || lab;
      }
      return o.value === '' ? '不做任何处理' : String(o.value);
    }
    if (o.value === '') return o.label || '（空）';
    return o.label && o.label !== o.value ? `${o.value} — ${o.label}` : String(o.value);
  },

  /** 参数表单模式：edit 可编辑 · view 只读查看 */
  normalizeParamMode(opts) {
    const o = opts || {};
    if (o.mode === 'view' || o.viewMode === true || o.readonly === true) return 'view';
    return 'edit';
  },

  renderParamInput(p, value, opts) {
    const options = opts || {};
    const userFacing = options.userFacing !== false;
    const viewMode = this.normalizeParamMode(options) === 'view';
    const val = value != null ? value : (p.default != null ? p.default : '');
    const req = (!viewMode && p.required) ? ' required' : '';
    // 查看态不渲染 placeholder，避免与真实值混淆
    const ph = viewMode ? '' : this.escapeAttr(p.placeholder || '');
    const phAttr = ph ? ` placeholder="${ph}"` : '';
    const key = this.escapeAttr(p.key);
    const compactCls = userFacing ? ' cmd-param-control-input' : '';
    const roAttr = viewMode ? ' readonly tabindex="-1"' : '';
    const disAttr = viewMode ? ' disabled tabindex="-1"' : '';
    if (p.type === 'boolean') {
      return `<select class="form-select param-field${compactCls}" data-key="${key}" data-type="boolean"${req}${disAttr}>
        <option value="true"${val === 'true' || val === true ? ' selected' : ''}>是</option>
        <option value="false"${val === 'false' || val === false ? ' selected' : ''}>否</option>
      </select>`;
    }
    if (p.type === 'enum' && p.options) {
      const cur = val == null ? '' : String(val);
      return `<select class="form-select param-field${compactCls}" data-key="${key}" data-type="enum"${req}${disAttr}>${
        this.normalizeEnumOptions(p.options).map(o => {
          const v = this.escapeAttr(o.value);
          const shown = this.enumOptionLabel(o, userFacing);
          return `<option value="${v}"${o.value === cur ? ' selected' : ''}>${this.escapeAttr(shown)}</option>`;
        }).join('')
      }</select>`;
    }
    if (p.type === 'number' || p.type === 'long') {
      return `<input class="form-input param-field${compactCls}" type="number" data-key="${key}" data-type="${p.type === 'long' ? 'long' : 'number'}" value="${this.escapeAttr(val)}"${phAttr}${req}${roAttr}>`;
    }
    if (p.type === 'days_ms') {
      // 界面与平台库按「天」；写入设备预期快照时后端换算为毫秒。历史毫秒值自动换算展示
      let days = '';
      if (val !== '' && val != null) {
        const n = Number(val);
        if (Number.isFinite(n)) {
          days = n >= 86400000 ? String(Math.round(n / 86400000)) : String(n);
        }
      }
      const dayPh = viewMode ? '' : (ph || this.escapeAttr('天数'));
      const dayPhAttr = dayPh ? ` placeholder="${dayPh}"` : '';
      return `<div class="param-days-ms">
        <input class="form-input param-field${compactCls}" type="number" min="1" step="1" data-key="${key}" data-type="days_ms" value="${this.escapeAttr(days)}"${dayPhAttr}${req}${roAttr}>
        <span class="param-days-ms-unit">天</span>
      </div>`;
    }
    if (p.type === 'array_string') {
      const text = Array.isArray(val) ? val.join('\n') : (val == null ? '' : String(val));
      const rows = userFacing ? 3 : 4;
      const arrPh = viewMode ? '' : (ph || this.escapeAttr('每行填写一项'));
      const arrPhAttr = arrPh ? ` placeholder="${arrPh}"` : '';
      return `<textarea class="form-input param-field${compactCls}" data-key="${key}" data-type="array_string" rows="${rows}"${arrPhAttr}${req}${roAttr}>${this.escapeAttr(text)}</textarea>`;
    }
    if (p.type === 'array_object' || p.type === 'json') {
      let text = '';
      if (typeof val === 'string') text = val;
      else if (val != null && val !== '') text = JSON.stringify(val, null, 2);
      const rows = userFacing ? 5 : 8;
      const jsonPh = viewMode ? '' : (ph || this.escapeAttr('按说明填写列表内容'));
      const jsonPhAttr = jsonPh ? ` placeholder="${jsonPh}"` : '';
      return `<textarea class="form-input param-field${compactCls}" data-key="${key}" data-type="array_object" rows="${rows}"${jsonPhAttr}${req}${roAttr}>${this.escapeAttr(text)}</textarea>`;
    }
    if (p.type === 'file') {
      const accept = this.escapeAttr(p.accept || '.cer,.crt,.pem,.p12,.pfx,.cert');
      const b64 = typeof val === 'string' ? val : '';
      const hasFile = !!b64;
      const status = viewMode
        ? (hasFile ? '已上传证书' : '未上传')
        : (hasFile ? '已上传，可重新选择替换' : '请选择要上传的证书文件');
      return `<div class="param-file-wrap">
        ${viewMode ? '' : `<input type="file" class="form-input param-file-pick${compactCls}" data-file-for="${key}" accept="${accept}">`}
        <input type="hidden" class="param-field" data-key="${key}" data-type="file" value="${this.escapeAttr(b64)}"${req}>
        <div class="cmd-param-file-status param-file-name">${this.escapeAttr(status)}</div>
        ${(!viewMode && hasFile) ? `<button type="button" class="btn btn-sm param-file-clear" data-file-clear="${key}">清除</button>` : ''}
      </div>`;
    }
    if (p.type === 'firewall_rules') {
      let initial = '[]';
      if (Array.isArray(val)) initial = JSON.stringify(val);
      else if (typeof val === 'string' && val.trim()) initial = val;
      return `<div class="fw-rules-picker" data-fw-key="${key}">
        <input type="hidden" class="param-field" data-key="${key}" data-type="firewall_rules" value="${this.escapeAttr(initial)}">
        <div class="fw-rules-list"></div>
        ${viewMode ? '' : '<button type="button" class="btn btn-sm fw-rule-add">+ 添加规则</button>'}
      </div>`;
    }
    if (p.type === 'app_install_select') {
      let initial = '[]';
      if (Array.isArray(val)) initial = JSON.stringify(val);
      else if (typeof val === 'string' && val.trim()) initial = val;
      return `<div class="app-install-picker" data-picker-key="${key}">
        <input type="hidden" class="param-field" data-key="${key}" data-type="app_install_select" value="${this.escapeAttr(initial)}">
        <div class="app-install-rows"></div>
        ${viewMode ? '' : '<button type="button" class="btn btn-sm app-install-add">+ 添加应用</button>'}
        <div class="app-install-loading cmd-param-hint" style="display:none">正在加载应用列表…</div>
        <div class="app-install-empty cmd-param-hint" style="display:none">暂无上架且含已发布版本的应用可选</div>
      </div>`;
    }
    if (p.type === 'app_multi_select') {
      let initial = '[]';
      if (Array.isArray(val)) initial = JSON.stringify(val);
      else if (typeof val === 'string' && val.trim()) initial = val;
      const valueField = ['bundleName', 'appId'].includes(p.valueField) ? p.valueField : 'id';
      // appRef：存 [{appId, appName}]；默认 scalar 存字符串数组（如 uninstallApps 的 bundleName）
      const valueShape = p.valueShape === 'appRef' ? 'appRef' : 'scalar';
      return `<div class="app-multi-dropdown" data-multi-key="${key}" data-value-field="${valueField}" data-value-shape="${valueShape}">
        <input type="hidden" class="param-field" data-key="${key}" data-type="app_multi_select" data-value-field="${valueField}" data-value-shape="${valueShape}" value="${this.escapeAttr(initial)}">
        <button type="button" class="form-select app-multi-trigger"${viewMode ? ' disabled tabindex="-1"' : ''} aria-expanded="false">
          <span class="app-multi-trigger-text">${viewMode ? '—' : '请选择应用'}</span>
          ${viewMode ? '' : '<span class="app-multi-caret">▾</span>'}
        </button>
        ${viewMode ? '' : `<div class="app-multi-panel" hidden>
          <div class="app-multi-panel-tools">
            <button type="button" class="btn-link app-multi-all">全选</button>
            <button type="button" class="btn-link app-multi-clear">清空</button>
          </div>
          <div class="app-multi-options"></div>
        </div>`}
        <div class="app-multi-loading cmd-param-hint" style="display:none">正在加载应用列表…</div>
      </div>`;
    }
    return `<input class="form-input param-field${compactCls}" type="text" data-key="${key}" data-type="string" value="${this.escapeAttr(val)}"${phAttr}${req}${roAttr}>`;
  },

  /** 加载应用管理目录：全部应用 ID + 可安装（上架且有已发布版本）应用 */
  async loadAppInstallCatalog(force) {
    if (!force && this._appInstallCatalogPromise) return this._appInstallCatalogPromise;
    this._appInstallCatalogPromise = (async () => {
      if (typeof MDMApi === 'undefined' || !MDMApi.listApps) {
        return { allAppIds: [], allApps: [], selectable: [] };
      }
      const items = [];
      let page = 1;
      let total = Infinity;
      while (items.length < total && page <= 20) {
        const data = await MDMApi.listApps({ page, page_size: 100 });
        const batch = (data && data.items) || [];
        total = Number(data && data.total) || batch.length;
        items.push(...batch);
        if (!batch.length) break;
        page += 1;
      }
      const allApps = items.map(a => ({
        id: String(a.id),
        name: a.app_name || a.app_code || String(a.id),
        appId: a.app_id || '',
        bundleName: a.bundle_name || ''
      }));
      // *AppIds 等其它策略仍使用应用基本信息中的 App ID
      const allAppIds = allApps.map(a => a.appId).filter(Boolean);
      const details = await Promise.all(
        items
          .filter(a => Number(a.status) === 1)
          .map(a => MDMApi.getApp(a.id).catch(() => null))
      );
      const selectable = [];
      details.forEach(app => {
        if (!app) return;
        // 版本「已发布」(status=2) 视为可下发；无已发布版本则不出现在下拉中
        const versions = (app.versions || []).filter(v => Number(v.status) === 2);
        if (!versions.length) return;
        const entry = allApps.find(a => a.id === String(app.id));
        const appId = (app.app_id || (entry && entry.appId) || '').trim();
        const bundleName = (app.bundle_name || (entry && entry.bundleName) || '').trim();
        if (entry) {
          if (!entry.appId && appId) entry.appId = appId;
          if (!entry.bundleName && bundleName) entry.bundleName = bundleName;
        }
        if (!appId || !bundleName) return;
        selectable.push({
          id: String(app.id),
          name: app.app_name || app.app_code || String(app.id),
          appId,
          bundleName,
          versions: versions.map(v => ({
            id: String(v.id),
            versionName: v.version_name || v.version_code || '',
            downloadUrl: v.download_url
              ? (v.download_url.startsWith('http') ? v.download_url : `${location.origin}${v.download_url}`)
              : ''
          }))
        });
      });
      const catalog = { allAppIds, allApps, selectable };
      this._appInstallCatalog = catalog;
      return catalog;
    })().catch(err => {
      this._appInstallCatalogPromise = null;
      throw err;
    });
    return this._appInstallCatalogPromise;
  },

  _appInstallAbsoluteUrl(url) {
    if (!url) return '';
    if (/^https?:\/\//i.test(url)) return url;
    return `${location.origin}${url.startsWith('/') ? '' : '/'}${url}`;
  },

  bindAppInstallPickers(container) {
    if (!container) return;
    const viewMode = this.isParamFormViewMode(container);
    container.querySelectorAll('.app-install-picker').forEach(picker => {
      if (picker.dataset.bound === '1') return;
      picker.dataset.bound = '1';
      if (viewMode) picker.classList.add('is-view');
      const hidden = picker.querySelector('.param-field[data-type="app_install_select"]');
      const rowsEl = picker.querySelector('.app-install-rows');
      const addBtn = picker.querySelector('.app-install-add');
      const loadingEl = picker.querySelector('.app-install-loading');
      const emptyEl = picker.querySelector('.app-install-empty');

      const readValue = () => {
        try {
          const raw = JSON.parse(hidden.value || '[]');
          return Array.isArray(raw) ? raw : [];
        } catch (_) {
          return [];
        }
      };

      const writeValue = (list) => {
        hidden.value = JSON.stringify(list || []);
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      };

      // 下拉 option 值为内部主键 id；协议字段 appId 为业务 App ID
      const resolveSelectable = (bizOrPk) => {
        const key = String(bizOrPk || '');
        if (!key) return null;
        return (this._appInstallCatalog?.selectable || []).find(
          a => a.appId === key || a.id === key
        ) || null;
      };
      const selectedAppIds = () => readValue()
        .map(x => {
          const hit = resolveSelectable(x.appId);
          return hit ? hit.id : '';
        })
        .filter(Boolean);

      const syncFromDomRows = () => {
        const catalog = this._appInstallCatalog || { selectable: [] };
        const list = [];
        rowsEl.querySelectorAll('.app-install-row').forEach(row => {
          const rowKey = row.querySelector('.app-install-app')?.value || '';
          const versionId = row.querySelector('.app-install-version')?.value || '';
          if (!rowKey || !versionId) return;
          const app = (catalog.selectable || []).find(a => a.id === rowKey);
          const ver = app && (app.versions || []).find(v => v.id === versionId);
          if (!app || !ver) return;
          list.push({
            appId: app.appId || '',
            bundleName: app.bundleName || '',
            version: ver.versionName || '',
            bundleDownloadUrl: this._appInstallAbsoluteUrl(ver.downloadUrl || '')
          });
        });
        writeValue(list);
      };

      const renderVersionOptions = (appId, selectedVersionId) => {
        const app = (this._appInstallCatalog?.selectable || []).find(a => a.id === appId);
        const vers = (app && app.versions) || [];
        if (!vers.length) return '<option value="">暂无已发布版本</option>';
        return `<option value="">请选择版本</option>${vers.map(v =>
          `<option value="${this.escapeAttr(v.id)}"${String(v.id) === String(selectedVersionId || '') ? ' selected' : ''}>${this.escapeAttr(v.versionName)}</option>`
        ).join('')}`;
      };

      const renderAppOptions = (selectedAppId, lockedIds) => {
        const apps = this._appInstallCatalog?.selectable || [];
        const opts = apps.filter(a => a.id === selectedAppId || !lockedIds.has(a.id));
        if (!opts.length && !selectedAppId) return '<option value="">暂无可选应用</option>';
        return `<option value="">请选择应用</option>${opts.map(a =>
          `<option value="${this.escapeAttr(a.id)}"${a.id === selectedAppId ? ' selected' : ''}>${this.escapeAttr(a.name)}</option>`
        ).join('')}`;
      };

      const mountRow = (item) => {
        const row = document.createElement('div');
        row.className = 'app-install-row';
        let rowKey = '';
        let versionId = '';
        let appLabel = '';
        let verLabel = '';
        if (item && item.appId) {
          const app = resolveSelectable(item.appId);
          if (app) {
            rowKey = app.id;
            appLabel = app.name || item.appId;
            const hit = (app.versions || []).find(v =>
              v.versionName === item.version || v.id === item.versionId
            );
            versionId = hit ? hit.id : '';
            verLabel = hit ? hit.versionName : (item.version || '');
          } else {
            appLabel = item.appId || '';
            verLabel = item.version || '';
          }
        }
        if (viewMode) {
          const empty = !appLabel && !verLabel;
          row.innerHTML = empty
            ? '<div class="text-muted" style="font-size:12px">未配置应用</div>'
            : `<div class="app-install-view-line">
                <span class="app-install-view-app">${this.escapeAttr(appLabel || '—')}</span>
                <span class="text-muted">·</span>
                <span class="app-install-view-ver">${this.escapeAttr(verLabel || '—')}</span>
              </div>`;
          rowsEl.appendChild(row);
          return;
        }
        const locked = new Set(selectedAppIds().filter(id => id !== rowKey));
        row.innerHTML = `
          <select class="form-select app-install-app">${renderAppOptions(rowKey, locked)}</select>
          <select class="form-select app-install-version"${rowKey ? '' : ' disabled'}>${rowKey ? renderVersionOptions(rowKey, versionId) : '<option value="">先选择应用</option>'}</select>
          <button type="button" class="btn btn-sm app-install-remove" title="移除">移除</button>`;
        rowsEl.appendChild(row);

        const appSel = row.querySelector('.app-install-app');
        const verSel = row.querySelector('.app-install-version');
        appSel.addEventListener('change', () => {
          const id = appSel.value;
          verSel.disabled = !id;
          verSel.innerHTML = id ? renderVersionOptions(id, '') : '<option value="">先选择应用</option>';
          // 刷新其它行可选应用
          refreshAllAppOptions();
          syncFromDomRows();
        });
        verSel.addEventListener('change', syncFromDomRows);
        row.querySelector('.app-install-remove').addEventListener('click', () => {
          row.remove();
          refreshAllAppOptions();
          syncFromDomRows();
        });
      };

      const refreshAllAppOptions = () => {
        const used = selectedAppIds();
        rowsEl.querySelectorAll('.app-install-row').forEach(row => {
          const appSel = row.querySelector('.app-install-app');
          const cur = appSel.value;
          const locked = new Set(used.filter(id => id !== cur));
          const keepVer = row.querySelector('.app-install-version')?.value || '';
          appSel.innerHTML = renderAppOptions(cur, locked);
          appSel.value = cur;
          if (cur) {
            const verSel = row.querySelector('.app-install-version');
            verSel.disabled = false;
            verSel.innerHTML = renderVersionOptions(cur, keepVer);
          }
        });
      };

      const rebuild = (list) => {
        rowsEl.innerHTML = '';
        const items = list || [];
        if (viewMode && !items.length) {
          rowsEl.innerHTML = '<div class="text-muted" style="font-size:12px">未配置应用</div>';
          return;
        }
        items.forEach(item => mountRow(item));
        if (!viewMode) refreshAllAppOptions();
      };

      if (!viewMode && addBtn) {
        addBtn.addEventListener('click', () => {
          const apps = this._appInstallCatalog?.selectable || [];
          const used = new Set(selectedAppIds());
          if (!apps.some(a => !used.has(a.id))) {
            if (window.MDMUtils && MDMUtils.toast) MDMUtils.toast('没有更多可添加的应用', 'info');
            return;
          }
          mountRow({});
          refreshAllAppOptions();
        });
      }

      if (loadingEl) loadingEl.style.display = '';
      this.loadAppInstallCatalog()
        .then(catalog => {
          if (loadingEl) loadingEl.style.display = 'none';
          const has = (catalog.selectable || []).length > 0;
          if (emptyEl) emptyEl.style.display = (!viewMode && !has) ? '' : 'none';
          if (addBtn) addBtn.style.display = (!viewMode && has) ? '' : 'none';
          rebuild(readValue());
          // 用目录回填后同步一次，补全 bundleName / url
          if (!viewMode) syncFromDomRows();
        })
        .catch(err => {
          if (loadingEl) {
            loadingEl.style.display = viewMode ? 'none' : '';
            if (!viewMode) loadingEl.textContent = err.message || '加载应用列表失败';
          }
          // 查看态即使目录失败也展示已保存的原始配置
          if (viewMode) rebuild(readValue());
        });
    });
  },

  /** 根据 visibleWhen 判断字段是否应对当前值可见 */
  isParamVisible(p, values) {
    const cond = p && p.visibleWhen;
    if (!cond) return true;
    const vals = values || {};
    return Object.keys(cond).every(k => {
      const expect = cond[k];
      const actual = vals[k];
      if (Array.isArray(expect)) return expect.includes(actual);
      return actual === expect;
    });
  },

  /**
   * 面向使用用户的紧凑参数表单（策略下发 / 初始策略共用）
   * @param {object|array} cmdOrParams 指令定义或 params 数组
   * @param {object} values 当前值
   * @param {object} [opts]
   */
  renderCommandParamForm(cmdOrParams, values, opts) {
    const options = opts || {};
    const mode = this.normalizeParamMode(options);
    const viewMode = mode === 'view';
    const dense = !!options.dense;
    // 查看态不折叠，完整展示当前配置
    const collapseOptional = !viewMode && !!options.collapseOptional;
    const hideHints = viewMode || dense || !!options.hideHints;
    const params = Array.isArray(cmdOrParams)
      ? cmdOrParams
      : ((cmdOrParams && cmdOrParams.params) || []);
    const vals = values || {};
    if (!params.length) {
      return `<p class="cmd-param-empty">${this.escapeAttr(options.emptyText || '该策略无需填写参数')}</p>`;
    }

    const isWide = (p) => p.type === 'app_install_select' || p.type === 'firewall_rules' || p.type === 'app_multi_select';
    // alwaysShow：始终展示在主区（不折叠进「更多选填项」）
    // visibleWhen：条件显示字段也放在主区，由显隐逻辑控制
    const isPrimary = (p) => !!(p.required || p.alwaysShow || p.visibleWhen || isWide(p));

    // 可见性判断时，缺省值回退到字段 default（如 securityType 默认 SAE）
    const effectiveVals = { ...vals };
    params.forEach(p => {
      if (effectiveVals[p.key] == null && p.default != null) {
        effectiveVals[p.key] = p.default;
      }
    });

    const inputOpts = { userFacing: true, mode };

    const renderRow = (p) => {
      const val = effectiveVals[p.key] != null ? effectiveVals[p.key] : '';
      const title = this.paramUserTitle(p);
      const hint = this.paramUserHint(p);
      const visible = this.isParamVisible(p, effectiveVals);
      let extra = '';
      if (!hideHints) {
        if ((p.type === 'array_object' || p.type === 'json') && (p.itemFields || []).length) {
          extra = `<div class="cmd-param-hint">每项包含：${p.itemFields.map(f => this.escapeAttr(f.desc || this.paramUserTitle(f))).join('；')}</div>`;
        } else if (p.type === 'array_string') {
          extra = hint ? '' : '<div class="cmd-param-hint">每行填写一项</div>';
        }
      }
      const whenAttr = p.visibleWhen
        ? ` data-visible-when="${this.escapeAttr(JSON.stringify(p.visibleWhen))}"`
        : '';
      const wide = isWide(p) ? ' cmd-param-row-wide' : '';
      const tip = hideHints && hint ? ` title="${this.escapeAttr(hint)}"` : '';
      return `<div class="cmd-param-row${wide}" data-param-key="${this.escapeAttr(p.key)}"${whenAttr}${visible ? '' : ' hidden'}>
        <label class="cmd-param-label"${tip}>${this.escapeAttr(title)}${(!viewMode && p.required) ? '<span class="cmd-param-req">*</span>' : ''}</label>
        <div class="cmd-param-control">${this.renderParamInput(p, val, inputOpts)}</div>
        ${!hideHints && hint ? `<div class="cmd-param-hint">${this.escapeAttr(hint)}</div>` : ''}
        ${extra}
      </div>`;
    };

    let primary = params;
    let optional = [];
    if (collapseOptional) {
      primary = params.filter(isPrimary);
      optional = params.filter(p => !isPrimary(p));
      // 若全部被归为高级，仍全部展示在主区，避免空表单
      if (!primary.length) {
        primary = params;
        optional = [];
      }
    }

    const formCls = [
      'cmd-param-form',
      dense ? 'cmd-param-form-dense' : '',
      viewMode ? 'cmd-param-form-view' : 'cmd-param-form-edit'
    ].filter(Boolean).join(' ');
    let html = `<div class="${formCls}" data-param-mode="${mode}">${primary.map(renderRow).join('')}`;
    if (optional.length) {
      html += `<details class="cmd-param-advanced">
        <summary>更多选填项（${optional.length}）</summary>
        <div class="cmd-param-advanced-body">${optional.map(renderRow).join('')}</div>
      </details>`;
    }
    html += '</div>';
    return html;
  },

  /** 按当前表单值刷新条件字段显隐；隐藏时清空值且不下发（查看态仅显隐，不清空） */
  applyParamVisibility(container) {
    if (!container) return;
    const viewMode = this.isParamFormViewMode(container);
    const form = container.querySelector('.cmd-param-form') || container;
    const draft = {};
    form.querySelectorAll('.param-field').forEach(el => {
      if (el.dataset.key) draft[el.dataset.key] = el.value;
    });
    // 查看态 select 可能 disabled，仍用当前选中值；缺省回退到 option[selected]
    form.querySelectorAll('select.param-field').forEach(el => {
      if (el.dataset.key && (draft[el.dataset.key] == null || draft[el.dataset.key] === '')) {
        const sel = el.querySelector('option[selected]') || el.options[el.selectedIndex];
        if (sel) draft[el.dataset.key] = sel.value;
      }
    });
    form.querySelectorAll('.cmd-param-row[data-visible-when]').forEach(row => {
      let cond = null;
      try { cond = JSON.parse(row.dataset.visibleWhen || '{}'); } catch (_) { cond = {}; }
      const visible = Object.keys(cond || {}).every(k => {
        const expect = cond[k];
        const actual = draft[k];
        if (Array.isArray(expect)) return expect.includes(actual);
        return actual === expect;
      });
      const wasHidden = row.hasAttribute('hidden');
      if (visible) {
        row.removeAttribute('hidden');
        if (!viewMode) {
          row.querySelectorAll('.param-field, .param-file-pick').forEach(el => {
            el.disabled = false;
          });
        }
      } else {
        row.setAttribute('hidden', '');
        if (viewMode) return;
        row.querySelectorAll('.param-field').forEach(el => {
          if (el.dataset.type === 'file') {
            el.value = '';
            const wrap = el.closest('.param-file-wrap');
            const pick = wrap && wrap.querySelector('.param-file-pick');
            const nameEl = wrap && wrap.querySelector('.param-file-name');
            const clearBtn = wrap && wrap.querySelector('.param-file-clear');
            if (pick) pick.value = '';
            if (nameEl) nameEl.textContent = '请选择要上传的证书文件';
            if (clearBtn) clearBtn.remove();
          } else if (el.tagName === 'SELECT') {
            const defOpt = el.querySelector('option[value="EAP_NONE"], option[value="PHASE2_NONE"], option[value=""]');
            el.value = defOpt ? defOpt.value : (el.options[0] ? el.options[0].value : '');
          } else {
            el.value = '';
          }
          el.disabled = true;
        });
        row.querySelectorAll('.param-file-pick').forEach(el => { el.disabled = true; });
        if (!wasHidden) {
          // 从显示切到隐藏时通知预览刷新
          const first = row.querySelector('.param-field');
          if (first) first.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });
  },

  bindParamVisibility(container) {
    if (!container || container.dataset.visibilityBound === '1') return;
    container.dataset.visibilityBound = '1';
    const run = () => this.applyParamVisibility(container);
    container.addEventListener('change', run);
    container.addEventListener('input', run);
    run();
  },

  isParamFormViewMode(root) {
    if (!root) return false;
    if (root.dataset && root.dataset.paramMode === 'view') return true;
    return !!root.querySelector?.('.cmd-param-form-view, [data-param-mode="view"]')
      || !!root.closest?.('.cmd-param-form-view, [data-param-mode="view"]');
  },

  mountCommandParamForm(container, cmdOrParams, values, opts) {
    if (!container) return;
    const mode = this.normalizeParamMode(opts);
    container.dataset.visibilityBound = '';
    container.dataset.paramMode = mode;
    container.classList.toggle('cmd-param-host-view', mode === 'view');
    container.classList.toggle('cmd-param-host-edit', mode !== 'view');
    container.innerHTML = this.renderCommandParamForm(cmdOrParams, values, opts);
    if (mode === 'view') {
      // 查看态仍需绑定展示型控件（应用列表回填等），但内部按 view 禁用操作
      this.bindParamVisibility(container);
      this.bindAppInstallPickers(container);
      this.bindAppMultiSelects(container);
      this.bindFirewallRulePickers(container);
      return;
    }
    this.bindParamFileInputs(container);
    this.bindParamVisibility(container);
    this.bindAppInstallPickers(container);
    this.bindAppMultiSelects(container);
    this.bindFirewallRulePickers(container);
  },

  bindFirewallRulePickers(container) {
    if (!container) return;
    const viewMode = this.isParamFormViewMode(container);
    container.querySelectorAll('.fw-rules-picker').forEach(picker => {
      if (picker.dataset.bound === '1') return;
      picker.dataset.bound = '1';
      if (viewMode) picker.classList.add('is-view');
      const hidden = picker.querySelector('.param-field[data-type="firewall_rules"]');
      const listEl = picker.querySelector('.fw-rules-list');
      const addBtn = picker.querySelector('.fw-rule-add');

      const readValue = () => {
        try {
          const raw = JSON.parse(hidden.value || '[]');
          return Array.isArray(raw) ? raw : [];
        } catch (_) {
          return [];
        }
      };

      const writeValue = (list) => {
        hidden.value = JSON.stringify(list || []);
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      };

      const syncFromDom = () => {
        if (viewMode) return;
        const list = [];
        listEl.querySelectorAll('.fw-rule-card').forEach(card => {
          const srcAddr = (card.querySelector('[data-fw="srcAddr"]')?.value || '').trim();
          const destAddr = (card.querySelector('[data-fw="destAddr"]')?.value || '').trim();
          const srcPort = (card.querySelector('[data-fw="srcPort"]')?.value || '').trim();
          const destPort = (card.querySelector('[data-fw="destPort"]')?.value || '').trim();
          if (!srcAddr && !destAddr && !srcPort && !destPort) return;
          list.push({ srcAddr, destAddr, srcPort, destPort });
        });
        writeValue(list);
        renumber();
      };

      const renumber = () => {
        listEl.querySelectorAll('.fw-rule-card').forEach((card, i) => {
          const title = card.querySelector('.fw-rule-title');
          if (title) title.textContent = `规则 ${i + 1}`;
        });
      };

      const mountCard = (item) => {
        const card = document.createElement('div');
        card.className = 'fw-rule-card';
        const it = item || {};
        if (viewMode) {
          card.innerHTML = `
            <div class="fw-rule-head">
              <span class="fw-rule-title">规则</span>
            </div>
            <div class="fw-rule-grid">
              <div class="fw-rule-field">
                <label>来源地址</label>
                <div class="cmd-param-view-text">${this.escapeAttr(it.srcAddr || '—')}</div>
              </div>
              <div class="fw-rule-field">
                <label>来源端口</label>
                <div class="cmd-param-view-text">${this.escapeAttr(it.srcPort || '—')}</div>
              </div>
              <div class="fw-rule-field">
                <label>目标地址</label>
                <div class="cmd-param-view-text">${this.escapeAttr(it.destAddr || '—')}</div>
              </div>
              <div class="fw-rule-field">
                <label>目标端口</label>
                <div class="cmd-param-view-text">${this.escapeAttr(it.destPort || '—')}</div>
              </div>
            </div>`;
          listEl.appendChild(card);
          renumber();
          return;
        }
        card.innerHTML = `
          <div class="fw-rule-head">
            <span class="fw-rule-title">规则</span>
            <button type="button" class="btn btn-sm fw-rule-remove">删除</button>
          </div>
          <div class="fw-rule-grid">
            <div class="fw-rule-field">
              <label>来源地址</label>
              <input class="form-input" data-fw="srcAddr" value="${this.escapeAttr(it.srcAddr || '')}" placeholder="如 192.168.1.1 或 192.168.1.1-192.168.22.66">
              <div class="fw-rule-tip">禁止访问本机的 IP / IP 段</div>
            </div>
            <div class="fw-rule-field">
              <label>来源端口</label>
              <input class="form-input" data-fw="srcPort" value="${this.escapeAttr(it.srcPort || '')}" placeholder="如 8080">
            </div>
            <div class="fw-rule-field">
              <label>目标地址</label>
              <input class="form-input" data-fw="destAddr" value="${this.escapeAttr(it.destAddr || '')}" placeholder="如 10.1.1.1">
              <div class="fw-rule-tip">禁止本机访问的 IP / IP 段</div>
            </div>
            <div class="fw-rule-field">
              <label>目标端口</label>
              <input class="form-input" data-fw="destPort" value="${this.escapeAttr(it.destPort || '')}" placeholder="如 8089">
            </div>
          </div>`;
        listEl.appendChild(card);
        card.querySelectorAll('input').forEach(el => {
          el.addEventListener('input', syncFromDom);
          el.addEventListener('change', syncFromDom);
        });
        card.querySelector('.fw-rule-remove').addEventListener('click', () => {
          card.remove();
          syncFromDom();
        });
        renumber();
      };

      if (!viewMode && addBtn) {
        addBtn.addEventListener('click', () => {
          mountCard({});
          syncFromDom();
        });
      }

      const initial = readValue();
      listEl.innerHTML = '';
      if (initial.length) initial.forEach(item => mountCard(item));
      else if (viewMode) {
        listEl.innerHTML = '<div class="text-muted" style="font-size:12px">无规则</div>';
      } else {
        mountCard({});
        syncFromDom();
      }
      if (!viewMode && initial.length) syncFromDom();
    });
  },

  bindAppMultiSelects(container) {
    if (!container) return;
    const viewMode = this.isParamFormViewMode(container);
    container.querySelectorAll('.app-multi-dropdown').forEach(wrap => {
      if (wrap.dataset.bound === '1') return;
      wrap.dataset.bound = '1';
      if (viewMode) wrap.classList.add('is-view');
      const hidden = wrap.querySelector('.param-field[data-type="app_multi_select"]');
      const trigger = wrap.querySelector('.app-multi-trigger');
      const triggerText = wrap.querySelector('.app-multi-trigger-text');
      const panel = wrap.querySelector('.app-multi-panel');
      const optionsEl = wrap.querySelector('.app-multi-options');
      const loadingEl = wrap.querySelector('.app-multi-loading');
      const btnAll = wrap.querySelector('.app-multi-all');
      const btnClear = wrap.querySelector('.app-multi-clear');
      const rawField = wrap.dataset.valueField || hidden.dataset.valueField || 'id';
      const valueField = ['bundleName', 'appId'].includes(rawField) ? rawField : 'id';
      const valueShape = (wrap.dataset.valueShape || hidden.dataset.valueShape || 'scalar') === 'appRef'
        ? 'appRef'
        : 'scalar';
      let appMap = {};
      let storedNameById = {};

      const optionValue = (app) => {
        if (valueField === 'bundleName') return String(app.bundleName || '').trim();
        if (valueField === 'appId') return String(app.appId || '').trim();
        return String(app.id || '');
      };

      const readRawItems = () => {
        try {
          const raw = JSON.parse(hidden.value || '[]');
          return Array.isArray(raw) ? raw : [];
        } catch (_) {
          return [];
        }
      };

      const readValues = () => {
        const items = readRawItems();
        if (valueShape === 'appRef') {
          storedNameById = {};
          return items.map(it => {
            if (typeof it === 'string') return String(it).trim();
            if (it && typeof it === 'object') {
              const id = String(it.appId || '').trim();
              const name = String(it.appName || '').trim();
              if (id && name) storedNameById[id] = name;
              return id;
            }
            return '';
          }).filter(Boolean);
        }
        return items.map(String).filter(Boolean);
      };

      const labelFor = (id) => (appMap[id] && appMap[id].name) || storedNameById[id] || id;

      const updateTriggerLabel = () => {
        const vals = readValues();
        if (!vals.length) {
          triggerText.textContent = viewMode ? '—' : '请选择应用';
          return;
        }
        const names = vals.map(labelFor);
        if (names.length <= 2) {
          triggerText.textContent = names.join('、');
        } else {
          triggerText.textContent = `已选 ${names.length} 个：${names.slice(0, 2).join('、')}…`;
        }
      };

      const syncFromChecks = () => {
        if (viewMode || !optionsEl) return;
        const vals = Array.from(optionsEl.querySelectorAll('input[type="checkbox"]:checked'))
          .map(el => el.value)
          .filter(Boolean);
        if (valueShape === 'appRef') {
          hidden.value = JSON.stringify(vals.map(v => ({
            appId: v,
            appName: (appMap[v] && appMap[v].name) || storedNameById[v] || v
          })));
        } else {
          hidden.value = JSON.stringify(vals);
        }
        updateTriggerLabel();
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      };

      const setOpen = (open) => {
        if (viewMode || !panel) return;
        if (open) {
          panel.hidden = false;
          trigger.setAttribute('aria-expanded', 'true');
          wrap.classList.add('is-open');
        } else {
          panel.hidden = true;
          trigger.setAttribute('aria-expanded', 'false');
          wrap.classList.remove('is-open');
        }
      };

      if (viewMode) {
        trigger.disabled = true;
        trigger.setAttribute('tabindex', '-1');
        updateTriggerLabel();
      } else {
        trigger.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (trigger.disabled) return;
          setOpen(panel.hidden);
        });
        panel?.addEventListener('click', (e) => e.stopPropagation());

        if (!this._appMultiOutsideBound) {
          this._appMultiOutsideBound = true;
          document.addEventListener('click', () => {
            document.querySelectorAll('.app-multi-dropdown.is-open').forEach(el => {
              el.classList.remove('is-open');
              const p = el.querySelector('.app-multi-panel');
              const t = el.querySelector('.app-multi-trigger');
              if (p) p.hidden = true;
              if (t) t.setAttribute('aria-expanded', 'false');
            });
          });
        }

        btnAll?.addEventListener('click', (e) => {
          e.preventDefault();
          optionsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = true; });
          syncFromChecks();
        });
        btnClear?.addEventListener('click', (e) => {
          e.preventDefault();
          optionsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; });
          syncFromChecks();
        });
      }

      if (loadingEl) loadingEl.style.display = '';
      this.loadAppInstallCatalog()
        .then(catalog => {
          if (loadingEl) loadingEl.style.display = 'none';
          const apps = (catalog.allApps || []).filter(a => optionValue(a));
          appMap = {};
          apps.forEach(a => { appMap[optionValue(a)] = a; });
          if (viewMode) {
            trigger.disabled = true;
            updateTriggerLabel();
            return;
          }
          const selected = new Set(readValues());
          if (!apps.length) {
            optionsEl.innerHTML = '<div class="cmd-param-hint">暂无应用</div>';
            trigger.disabled = true;
            triggerText.textContent = '暂无应用';
            return;
          }
          trigger.disabled = false;
          optionsEl.innerHTML = apps.map(a => {
            const v = optionValue(a);
            return `
            <label class="app-multi-option">
              <input type="checkbox" value="${this.escapeAttr(v)}"${selected.has(v) ? ' checked' : ''}>
              <span>${this.escapeAttr(a.name)}</span>
            </label>`;
          }).join('');
          optionsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', syncFromChecks);
          });
          updateTriggerLabel();
        })
        .catch(err => {
          if (loadingEl) {
            loadingEl.style.display = viewMode ? 'none' : '';
            if (!viewMode) loadingEl.textContent = err.message || '加载应用列表失败';
          }
          if (viewMode) updateTriggerLabel();
        });
    });
  },

  /** 绑定 type=file 参数：选文件后读为标准 Base64 写入隐藏域 */
  bindParamFileInputs(container) {
    if (!container) return;
    container.querySelectorAll('.param-file-pick').forEach(pick => {
      if (pick.dataset.bound === '1') return;
      pick.dataset.bound = '1';
      pick.addEventListener('change', () => {
        const key = pick.dataset.fileFor;
        const wrap = pick.closest('.param-file-wrap') || pick.parentElement;
        const hidden = wrap.querySelector(`.param-field[data-key="${key}"]`);
        const nameEl = wrap.querySelector('.param-file-name');
        const file = pick.files && pick.files[0];
        if (!hidden) return;
        if (!file) {
          hidden.value = '';
          if (nameEl) nameEl.textContent = '请选择要上传的证书文件';
          hidden.dispatchEvent(new Event('change', { bubbles: true }));
          return;
        }
        if (nameEl) nameEl.textContent = `正在读取 ${file.name}…`;
        const reader = new FileReader();
        reader.onload = () => {
          const result = String(reader.result || '');
          const b64 = result.includes(',') ? result.split(',')[1] : result;
          hidden.value = b64 || '';
          if (nameEl) nameEl.textContent = `已选择：${file.name}`;
          let clearBtn = wrap.querySelector('.param-file-clear');
          if (!clearBtn) {
            clearBtn = document.createElement('button');
            clearBtn.type = 'button';
            clearBtn.className = 'btn btn-sm param-file-clear';
            clearBtn.dataset.fileClear = key;
            clearBtn.textContent = '清除';
            wrap.appendChild(clearBtn);
            this._bindParamFileClear(clearBtn, container);
          }
          hidden.dispatchEvent(new Event('change', { bubbles: true }));
        };
        reader.onerror = () => {
          hidden.value = '';
          if (nameEl) nameEl.textContent = '读取失败，请重试';
          hidden.dispatchEvent(new Event('change', { bubbles: true }));
        };
        reader.readAsDataURL(file);
      });
    });
    container.querySelectorAll('.param-file-clear').forEach(btn => this._bindParamFileClear(btn, container));
  },

  _bindParamFileClear(btn, container) {
    if (!btn || btn.dataset.bound === '1') return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => {
      const key = btn.dataset.fileClear;
      const wrap = btn.closest('.param-file-wrap') || btn.parentElement;
      const hidden = wrap.querySelector(`.param-field[data-key="${key}"]`);
      const pick = wrap.querySelector('.param-file-pick');
      const nameEl = wrap.querySelector('.param-file-name');
      if (hidden) hidden.value = '';
      if (pick) pick.value = '';
      if (nameEl) nameEl.textContent = '请选择要上传的证书文件';
      btn.remove();
      if (hidden) hidden.dispatchEvent(new Event('change', { bubbles: true }));
    });
  },

  collectParamValues(container) {
    const params = {};
    if (!container) return params;
    container.querySelectorAll('.param-field').forEach(el => {
      const row = el.closest('.cmd-param-row');
      if (row && row.hasAttribute('hidden')) return;
      if (el.disabled) return;
      const key = el.dataset.key;
      let val = el.value;
      const type = el.dataset.type;
      if (type === 'boolean') val = val === 'true';
      else if ((type === 'number' || type === 'long') && val !== '') val = Number(val);
      else if (type === 'days_ms') {
        // 平台按天入库；毫秒换算在写入预期快照时由后端完成
        if (val === '' || val == null) val = '';
        else {
          const days = Number(val);
          val = Number.isFinite(days) ? Math.max(1, Math.round(days)) : val;
        }
      }
      else if (type === 'array_string') {
        val = String(val || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      } else if (type === 'array_object') {
        const raw = String(val || '').trim();
        if (!raw) val = [];
        else {
          try { val = JSON.parse(raw); }
          catch (_) { el.dataset.parseError = '1'; val = raw; }
        }
      } else if (type === 'file') {
        val = String(val || '');
      } else if (type === 'app_multi_select') {
        const shape = el.dataset.valueShape === 'appRef' ? 'appRef' : 'scalar';
        try {
          const parsed = JSON.parse(String(val || '[]'));
          if (!Array.isArray(parsed)) val = [];
          else if (shape === 'appRef') {
            val = parsed.map(item => {
              if (typeof item === 'string') {
                const id = String(item).trim();
                return id ? { appId: id, appName: id } : null;
              }
              if (item && typeof item === 'object') {
                const appId = String(item.appId || '').trim();
                if (!appId) return null;
                const appName = String(item.appName || '').trim() || appId;
                return { appId, appName };
              }
              return null;
            }).filter(Boolean);
          } else {
            val = parsed.map(String).filter(Boolean);
          }
        } catch (_) {
          val = [];
        }
      } else if (type === 'app_install_select' || type === 'firewall_rules') {
        // 对象数组，不可 map(String)，否则会变成 "[object Object]"
        try {
          const parsed = JSON.parse(String(val || '[]'));
          val = Array.isArray(parsed) ? parsed : [];
        } catch (_) {
          val = [];
        }
      }
      params[key] = val;
    });
    return params;
  },

  buildCommandPayload(cmd, params) {
    const c = typeof cmd === 'string' ? this.findCommand(cmd) : cmd;
    if (!c) return JSON.stringify({ param: params || {} }, null, 2);
    const param = { ...(params || {}) };
    // 应用安装管理：仅保留 currentApps / uninstallApps
    if (c.code === 'APP_MANAGEMENT') {
      delete param.totalApps;
      if (!Array.isArray(param.currentApps)) param.currentApps = [];
      if (!Array.isArray(param.uninstallApps)) param.uninstallApps = [];
      else param.uninstallApps = param.uninstallApps.map(String).filter(Boolean);
    }
    // 应用配置管理：三名单为 {appId, appName}[]
    if (c.code === 'APP_CONFIG_MANAGEMENT') {
      const toAppRef = (list) => {
        if (!Array.isArray(list)) return [];
        return list.map(item => {
          if (typeof item === 'string') {
            const id = String(item).trim();
            return id ? { appId: id, appName: id } : null;
          }
          if (item && typeof item === 'object') {
            const appId = String(item.appId || '').trim();
            if (!appId) return null;
            return { appId, appName: String(item.appName || '').trim() || appId };
          }
          return null;
        }).filter(Boolean);
      };
      param.allowAppIds = toAppRef(param.allowAppIds);
      param.disallowAppIds = toAppRef(param.disallowAppIds);
      param.disallowedUninstallAppIds = toAppRef(param.disallowedUninstallAppIds);
    }
    const body = { [c.protocolKey || 'sceneCode']: c.protocolCode || c.code, param };
    return JSON.stringify(body, null, 2);
  },

  routes: {
    dashboard: '/index.html',
    users: '/pages/platform/users.html',
    userForm: '/pages/platform/user-form.html',
    rolePermission: '/pages/platform/role-permission.html',
    /** 兼容旧链接 → 平台基础管理 */
    settings: '/pages/platform/users.html',
    devices: '/pages/devices/devices.html',
    deviceDetail: '/pages/devices/device-detail.html',
    /** 兼容旧预录入/导入页 → 设备列表 */
    deviceForm: '/pages/devices/devices.html',
    deviceImport: '/pages/devices/devices.html',
    deviceGroups: '/pages/members/groups.html',
    members: '/pages/members/members.html',
    initialPolicy: '/pages/members/initial-policy.html',
    initialPolicyForm: '/pages/members/initial-policy-form.html',
    apps: '/pages/apps/apps.html',
    appDetail: '/pages/apps/app-detail.html',
    appForm: '/pages/apps/app-form.html',
    appVersionForm: '/pages/apps/app-version-form.html',
    /** 兼容旧指令/策略库/任务页 → 策略下发 */
    commands: '/pages/scenes/scene-dispatch.html',
    commandForm: '/pages/scenes/scene-dispatch.html',
    dispatch: '/pages/scenes/scene-dispatch.html',
    dispatchCreate: '/pages/scenes/scene-dispatch-create.html',
    dispatchDetail: '/pages/scenes/scene-dispatch-detail.html',
    scenes: '/pages/scenes/scene-dispatch.html',
    sceneForm: '/pages/scenes/scene-dispatch.html',
    sceneDispatch: '/pages/scenes/scene-dispatch.html',
    sceneDispatchCreate: '/pages/scenes/scene-dispatch-create.html',
    sceneDispatchDetail: '/pages/scenes/scene-dispatch-detail.html'
  },

  /** 策略类型文案（与客户端统一：紧急 / 普通） */
  policyLevelLabel(level) {
    return level === 'urgent' ? '紧急' : '普通';
  },

  policyLevelBadge(level) {
    if (level === 'urgent') return '<span class="tag tag-orange">紧急策略</span>';
    return '<span class="tag tag-blue">普通策略</span>';
  },

  /** 策略最晚延迟执行时间选项（0 = 立刻执行 → 紧急策略） */
  policyDeadlineHourOptions: [
    { value: 0, label: '立刻执行' },
    { value: 1, label: '1 小时' },
    { value: 2, label: '2 小时' },
    { value: 4, label: '4 小时' },
    { value: 8, label: '8 小时' },
    { value: 12, label: '12 小时' },
    { value: 24, label: '24 小时' }
  ],

  /** 由「最久 N 小时」换算截止时间（本地 datetime-local 字符串） */
  deadlineFromHours(hours) {
    const h = Number(hours);
    if (!h || h <= 0) return null;
    const d = new Date(Date.now() + h * 60 * 60 * 1000);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  },

  /** @deprecated 兼容旧调用：默认按 4 小时换算 */
  defaultPolicyDeadlineLocal() {
    return this.deadlineFromHours(4);
  },

  /**
   * 下发表单：策略最晚延迟执行时间
   * 选「立刻执行」时策略类型为紧急，其余为普通
   */
  renderPolicyDispatchFields(opts) {
    const level = (opts && opts.level) || 'normal';
    let hours = (opts && opts.deadlineHours) != null ? Number(opts.deadlineHours) : 4;
    if (level === 'urgent') hours = 0;
    if (!Number.isFinite(hours) || hours < 0) hours = 4;
    const options = this.policyDeadlineHourOptions.map(o =>
      `<option value="${o.value}"${Number(o.value) === hours ? ' selected' : ''}>${o.label}</option>`
    ).join('');
    return `
      <div class="form-item" id="deadline-wrap">
        <label class="form-label">策略最晚延迟执行时间 <span style="color:var(--error)">*</span></label>
        <select class="form-select" id="policy-deadline-hours">${options}</select>
      </div>`;
  },

  bindPolicyDispatchFields(root) {
    const scope = root || document;
    const hoursEl = scope.querySelector('#policy-deadline-hours');
    const readHours = () => {
      if (!hoursEl) return 4;
      const h = Number(hoursEl.value);
      return Number.isFinite(h) ? h : 4;
    };
    const isImmediate = () => readHours() <= 0;
    return {
      /** 立刻执行 → urgent，否则 normal */
      getLevel: () => (isImmediate() ? 'urgent' : 'normal'),
      /** 选中的时限（小时），立刻执行返回 null */
      getDeadlineHours: () => (isImmediate() ? null : (readHours() || 4)),
      /** 时限文案，如「立刻执行」「4 小时」 */
      getDeadlineLabel: () => {
        const h = readHours();
        const hit = MDMUtils.policyDeadlineHourOptions.find(o => Number(o.value) === h);
        return hit ? hit.label : (h <= 0 ? '立刻执行' : `${h} 小时`);
      },
      /** 换算后的截止时间（本地）；立刻执行返回 null */
      getDeadline: () => {
        if (isImmediate()) return null;
        return MDMUtils.deadlineFromHours(readHours() || 4);
      }
    };
  },

  /** 场景开放参数表单：仅展示 scene.openParams 中的字段（用户向紧凑格式） */
  renderSceneOpenParams(scene) {
    if (!scene) return '<p class="cmd-param-empty">未选择策略</p>';
    const open = scene.openParams || [];
    const stepParams = {};
    (scene.steps || []).forEach(s => Object.assign(stepParams, s.params || {}));
    const fields = [];
    const seen = new Set();
    const values = {};
    (scene.steps || []).forEach(step => {
      const cmd = this.findCommand(step.code);
      (cmd.params || []).forEach(p => {
        if (open.length && !open.includes(p.key)) return;
        if (seen.has(p.key)) return;
        seen.add(p.key);
        fields.push(p);
        values[p.key] = stepParams[p.key] != null ? stepParams[p.key] : (p.default != null ? p.default : '');
      });
    });
    return this.renderCommandParamForm(fields, values, {
      emptyText: '该策略无开放参数，将使用默认配置下发'
    });
  },

  href(key, query) {
    const base = this.routes[key];
    if (!base) return key;
    if (!query) return base;
    if (typeof query === 'string') return base + (query.startsWith('?') ? query : '?' + query);
    const qs = Object.entries(query)
      .filter(([, v]) => v != null && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    return qs ? `${base}?${qs}` : base;
  },

  /** 手机号 / 邮箱格式（空值视为合法，由必填规则另行约束） */
  isPhone(v) {
    return !v || /^1[3-9]\d{9}$/.test(v);
  },
  isEmail(v) {
    return !v || /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(v);
  },

  _eyeOpen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
  _eyeOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',

  _filePickerIcon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',

  _hapPkgRemoveIcon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>',

  /**
   * HAP 安装包字段：未上传用虚线选择区；已上传显示图标卡片（含删除）。
   * @param {{ fieldId?: string, zoneId?: string, inputId?: string, pickerWrapId?: string, previewId?: string, fileName?: string, fileSize?: number|null }} opts
   */
  hapPackageFieldHtml(opts = {}) {
    const fieldId = opts.fieldId || 'hap-pkg-field';
    const zoneId = opts.zoneId || 'pkg-upload';
    const inputId = opts.inputId || 'pkg-file';
    const pickerWrapId = opts.pickerWrapId || 'pkg-picker-wrap';
    const previewId = opts.previewId || 'pkg-preview';
    const fileName = (opts.fileName || '').trim();
    const filled = !!fileName;
    const sizeText = this.fmtFileSize(opts.fileSize);
    return `<div class="hap-pkg-field" id="${this.escapeAttr(fieldId)}">
      <div class="hap-pkg-picker-wrap" id="${this.escapeAttr(pickerWrapId)}"${filled ? ' hidden' : ''}>
        ${this.filePickerHtml({
          zoneId,
          inputId,
          accept: '.hap,application/octet-stream',
          title: '点击选择 .hap 安装包',
          compact: true
        })}
      </div>
      <div class="hap-pkg-preview" id="${this.escapeAttr(previewId)}"${filled ? '' : ' hidden'}>
        <img class="hap-pkg-icon" src="${this.HAP_PACKAGE_ICON}" alt="HAP 安装包" width="52" height="52">
        <div class="hap-pkg-preview-meta">
          <div class="hap-pkg-name">${this.escapeAttr(fileName || '安装包.hap')}</div>
          <div class="hap-pkg-size"${sizeText ? '' : ' hidden'}>${this.escapeAttr(sizeText)}</div>
        </div>
        <button type="button" class="hap-pkg-remove" title="删除安装包" aria-label="删除安装包">${this._hapPkgRemoveIcon}<span>删除</span></button>
      </div>
    </div>`;
  },

  /**
   * 绑定 HAP 安装包字段。返回 { getFile, hasPackage, clear }。
   * @param {{ zoneId?: string, inputId?: string, pickerWrapId?: string, previewId?: string, fileName?: string, fileSize?: number|null, onChange?: (file: File|null) => void }} opts
   */
  bindHapPackageField(opts = {}) {
    const zoneId = opts.zoneId || 'pkg-upload';
    const inputId = opts.inputId || 'pkg-file';
    const pickerWrap = document.getElementById(opts.pickerWrapId || 'pkg-picker-wrap');
    const preview = document.getElementById(opts.previewId || 'pkg-preview');
    const nameEl = preview && preview.querySelector('.hap-pkg-name');
    const sizeEl = preview && preview.querySelector('.hap-pkg-size');
    const removeBtn = preview && preview.querySelector('.hap-pkg-remove');
    let selectedFile = null;
    let keepExisting = !!(opts.fileName || '').trim();

    const showPicker = () => {
      if (pickerWrap) pickerWrap.hidden = false;
      if (preview) preview.hidden = true;
    };
    const showPreview = (fileName, fileSize) => {
      if (nameEl) nameEl.textContent = fileName || '安装包.hap';
      if (sizeEl) {
        const text = this.fmtFileSize(fileSize);
        sizeEl.textContent = text;
        sizeEl.hidden = !text;
      }
      if (pickerWrap) pickerWrap.hidden = true;
      if (preview) preview.hidden = false;
    };

    const picker = this.bindFilePicker({
      zoneId,
      inputId,
      acceptExt: ['.hap'],
      emptyTitle: '点击选择 .hap 安装包',
      onChange(file) {
        selectedFile = file;
        if (file) {
          keepExisting = false;
          showPreview(file.name, file.size);
        } else {
          showPicker();
        }
        if (opts.onChange) opts.onChange(file);
      }
    });

    removeBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      selectedFile = null;
      keepExisting = false;
      picker.reset();
      showPicker();
      if (opts.onChange) opts.onChange(null);
    });

    return {
      getFile: () => selectedFile,
      hasPackage: () => !!(selectedFile || keepExisting),
      clear() {
        selectedFile = null;
        keepExisting = false;
        picker.reset();
        showPicker();
      }
    };
  },

  /**
   * 统一附件选择区 HTML（隐藏原生 file，用虚线框触发）。
   * @param {{ zoneId: string, inputId: string, accept?: string, title?: string, hint?: string, metaId?: string, metaText?: string, compact?: boolean }} opts
   */
  filePickerHtml(opts = {}) {
    const zoneId = opts.zoneId || '';
    const inputId = opts.inputId || '';
    const accept = opts.accept ? ` accept="${this.escapeAttr(opts.accept)}"` : '';
    const title = this.escapeAttr(opts.title || '点击选择文件');
    const hint = opts.hint ? `<div class="file-picker-hint">${this.escapeAttr(opts.hint)}</div>` : '';
    const compact = opts.compact ? ' is-compact' : '';
    const filled = opts.filled ? ' is-filled' : '';
    const metaId = opts.metaId || '';
    const metaText = opts.metaText != null ? opts.metaText : '尚未选择文件';
    const meta = metaId
      ? `<div class="file-picker-meta" id="${this.escapeAttr(metaId)}">${this.escapeAttr(metaText)}</div>`
      : '';
    return `<div class="file-picker${compact}${filled}" id="${this.escapeAttr(zoneId)}" role="button" tabindex="0">
      <div class="file-picker-icon">${this._filePickerIcon}</div>
      <div class="file-picker-title">${title}</div>
      ${hint}
    </div>
    <input type="file" id="${this.escapeAttr(inputId)}"${accept} hidden>
    ${meta}`;
  },

  /**
   * 绑定统一附件选择区。返回 { reset } 便于弹窗复用时清空。
   * @param {{ zoneId: string, inputId: string, metaId?: string, acceptExt?: string[], emptyTitle?: string, emptyMeta?: string, emptyHint?: string, filledHint?: string, onChange?: (file: File|null) => void }} opts
   */
  bindFilePicker(opts = {}) {
    const zone = document.getElementById(opts.zoneId);
    const input = document.getElementById(opts.inputId);
    if (!zone || !input) return { reset() {} };
    const meta = opts.metaId ? document.getElementById(opts.metaId) : null;
    const hintEl = zone.querySelector('.file-picker-hint');
    const emptyTitle = opts.emptyTitle || '点击选择文件';
    const emptyMeta = opts.emptyMeta || '尚未选择文件';
    const emptyHint = opts.emptyHint;
    const filledHint = opts.filledHint;
    const exts = (opts.acceptExt || []).map(e => String(e).toLowerCase());

    const setEmpty = () => {
      zone.classList.remove('is-filled', 'is-dragover');
      const titleEl = zone.querySelector('.file-picker-title');
      if (titleEl) titleEl.textContent = emptyTitle;
      if (meta) meta.textContent = emptyMeta;
      if (hintEl && emptyHint != null) hintEl.textContent = emptyHint;
      input.value = '';
    };

    const setFile = (file, silent) => {
      if (!file) {
        setEmpty();
        if (!silent && opts.onChange) opts.onChange(null);
        return;
      }
      const name = (file.name || '').toLowerCase();
      if (exts.length && !exts.some(ext => name.endsWith(ext))) {
        this.toast(`仅支持 ${exts.join(' / ')} 文件`, 'error');
        setEmpty();
        if (!silent && opts.onChange) opts.onChange(null);
        return;
      }
      zone.classList.add('is-filled');
      zone.classList.remove('is-dragover');
      const titleEl = zone.querySelector('.file-picker-title');
      if (titleEl) titleEl.textContent = file.name;
      if (meta) {
        const kb = file.size < 1024
          ? `${file.size} B`
          : file.size < 1024 * 1024
            ? `${(file.size / 1024).toFixed(1)} KB`
            : `${(file.size / 1024 / 1024).toFixed(2)} MB`;
        meta.textContent = `已选择 · ${kb}`;
      }
      if (hintEl && filledHint != null) hintEl.textContent = filledHint;
      if (!silent && opts.onChange) opts.onChange(file);
    };

    if (zone.dataset.pickerBound === '1') {
      return {
        reset: setEmpty,
        setFile(file) { setFile(file, true); }
      };
    }
    zone.dataset.pickerBound = '1';

    const open = () => input.click();
    zone.addEventListener('click', open);
    zone.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open();
      }
    });
    input.addEventListener('change', () => {
      setFile(input.files && input.files[0] ? input.files[0] : null);
    });

    zone.addEventListener('dragover', e => {
      e.preventDefault();
      zone.classList.add('is-dragover');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('is-dragover'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('is-dragover');
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      try {
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
      } catch (_) {
        /* 部分环境不支持赋值 files，仍回调文件 */
      }
      setFile(file);
    });

    return {
      reset: setEmpty,
      setFile(file) { setFile(file, true); }
    };
  },

  /** 平台管理员密码规则：6–18 位，须同时含字母与数字（大小写/特殊符号不限） */
  PLATFORM_PASSWORD_HINT: '密码须为 6-18 位，且同时包含字母和数字',

  /**
   * 校验平台管理员新密码格式。通过返回 null，失败返回提示文案。
   * 仅用于新建/重置/修改时的「新密码」；登录与旧密码不调用本方法。
   */
  validatePlatformPassword(password) {
    const pwd = password == null ? '' : String(password);
    if (!/^(?=.*[A-Za-z])(?=.*\d).{6,18}$/.test(pwd)) {
      return this.PLATFORM_PASSWORD_HINT;
    }
    return null;
  },

  /** 带眼睛按钮的密码输入框 HTML */
  passwordInputHtml(attrs = {}) {
    const id = attrs.id || '';
    const name = attrs.name ? ` name="${attrs.name}"` : '';
    const placeholder = attrs.placeholder ? ` placeholder="${attrs.placeholder}"` : '';
    const required = attrs.required ? ' required' : '';
    const extraClass = attrs.className ? ` ${attrs.className}` : '';
    const value = attrs.value != null ? ` value="${String(attrs.value).replace(/"/g, '&quot;')}"` : '';
    return `<div class="password-field">
      <input class="form-input${extraClass}" type="password" id="${id}"${name}${placeholder}${required}${value} autocomplete="${attrs.autocomplete || 'off'}">
      <button type="button" class="password-toggle" data-pwd-toggle aria-label="显示/隐藏密码" title="显示/隐藏密码">${this._eyeOpen}</button>
    </div>`;
  },

  /** 绑定容器内所有密码眼睛按钮（可重复调用，已绑过的会跳过） */
  bindPasswordToggles(root = document) {
    const scope = typeof root === 'string' ? document.querySelector(root) : root;
    if (!scope) return;
    scope.querySelectorAll('[data-pwd-toggle]').forEach(btn => {
      if (btn.dataset.bound === '1') return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', () => {
        const wrap = btn.closest('.password-field');
        const input = wrap && wrap.querySelector('input');
        if (!input) return;
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        btn.innerHTML = show ? this._eyeOff : this._eyeOpen;
        btn.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
      });
    });
  }
};
